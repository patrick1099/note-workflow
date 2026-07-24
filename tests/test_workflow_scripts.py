from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ACTION_ENGINE = PLUGIN_ROOT / "scripts" / "action_engine.py"
NOTE_STATUS = PLUGIN_ROOT / "scripts" / "note_status.py"


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=environment,
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class ActionEngineTests(unittest.TestCase):
    def test_archive_render_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "inbox").mkdir()
            (root / "inbox" / "a.md").write_text("# A\n", encoding="utf-8")
            plan_path = root / "plan.json"
            report_path = root / "archive-v1.md"
            write_json(
                plan_path,
                {
                    "version": 1,
                    "stage": "archive",
                    "title": "Archive v1",
                    "actions": [
                        {
                            "id": "F-001",
                            "type": "mkdir",
                            "path": "knowledge",
                            "summary": "Create knowledge folder",
                            "reason": "Stable reusable topic",
                            "dependencies": [],
                        },
                        {
                            "id": "M-001",
                            "type": "move",
                            "source": "inbox/a.md",
                            "target": "knowledge/a.md",
                            "summary": "Move accepted note",
                            "reason": "The note is reusable",
                            "dependencies": ["F-001"],
                        },
                    ],
                },
            )
            rendered = run_script(
                ACTION_ENGINE,
                "render",
                "--vault",
                str(root),
                "--plan",
                str(plan_path),
                "--report",
                str(report_path),
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            report = report_path.read_text(encoding="utf-8")
            report = report.replace("- [ ] `F-001`", "- [x] `F-001`")
            report = report.replace("- [ ] `M-001`", "- [x] `M-001`")
            report_path.write_text(report, encoding="utf-8")

            applied = run_script(
                ACTION_ENGINE,
                "apply",
                "--vault",
                str(root),
                "--report",
                str(report_path),
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertFalse((root / "inbox" / "a.md").exists())
            self.assertEqual(
                (root / "knowledge" / "a.md").read_text(encoding="utf-8"),
                "# A\n",
            )
            backups = list(
                (root / ".note-workflow-backups").rglob("inbox/a.md")
            )
            self.assertEqual(len(backups), 1)
            self.assertTrue(list(root.glob("archive-v1.receipt-*.json")))

    def test_link_action_is_atomic_across_two_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "A.md").write_text("A explains UART.\n", encoding="utf-8")
            (root / "B.md").write_text("B uses TCP.\n", encoding="utf-8")
            plan_path = root / "plan.json"
            report_path = root / "links-v1.md"
            write_json(
                plan_path,
                {
                    "version": 1,
                    "stage": "links",
                    "title": "Links v1",
                    "actions": [
                        {
                            "id": "L-001",
                            "type": "edit",
                            "summary": "Add prerequisite relation",
                            "relation": "前置知识",
                            "reason": "B depends on A",
                            "dependencies": [],
                            "changes": [
                                {
                                    "path": "A.md",
                                    "replacements": [
                                        {
                                            "old": "A explains UART.",
                                            "new": "A explains UART. 后续应用：[[B]]",
                                            "count": 1,
                                        }
                                    ],
                                },
                                {
                                    "path": "B.md",
                                    "replacements": [
                                        {
                                            "old": "B uses TCP.",
                                            "new": "B uses TCP. 前置知识：[[A]]",
                                            "count": 1,
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                },
            )
            rendered = run_script(
                ACTION_ENGINE,
                "render",
                "--vault",
                str(root),
                "--plan",
                str(plan_path),
                "--report",
                str(report_path),
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            report = report_path.read_text(encoding="utf-8").replace(
                "- [ ] `L-001`", "- [x] `L-001`"
            )
            report_path.write_text(report, encoding="utf-8")
            applied = run_script(
                ACTION_ENGINE,
                "apply",
                "--vault",
                str(root),
                "--report",
                str(report_path),
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertIn("[[B]]", (root / "A.md").read_text(encoding="utf-8"))
            self.assertIn("[[A]]", (root / "B.md").read_text(encoding="utf-8"))

    def test_protected_report_text_cannot_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan_path = root / "plan.json"
            report_path = root / "decision-v1.md"
            write_json(
                plan_path,
                {
                    "version": 1,
                    "stage": "archive",
                    "title": "Decision v1",
                    "actions": [
                        {
                            "id": "D-001",
                            "type": "decision",
                            "summary": "Keep current location",
                            "reason": "It still belongs to the project",
                            "dependencies": [],
                        }
                    ],
                },
            )
            rendered = run_script(
                ACTION_ENGINE,
                "render",
                "--vault",
                str(root),
                "--plan",
                str(plan_path),
                "--report",
                str(report_path),
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            report = report_path.read_text(encoding="utf-8")
            report = report.replace("It still belongs", "It no longer belongs")
            report = report.replace("- [ ] `D-001`", "- [x] `D-001`")
            report_path.write_text(report, encoding="utf-8")
            applied = run_script(
                ACTION_ENGINE,
                "apply",
                "--vault",
                str(root),
                "--report",
                str(report_path),
            )
            self.assertEqual(applied.returncode, 2)
            self.assertIn("受保护正文已变化", applied.stderr)

    def test_file_drift_rejects_checked_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            note = root / "A.md"
            note.write_text("old\n", encoding="utf-8")
            plan_path = root / "plan.json"
            report_path = root / "links-v1.md"
            write_json(
                plan_path,
                {
                    "version": 1,
                    "stage": "links",
                    "title": "Links v1",
                    "actions": [
                        {
                            "id": "R-001",
                            "type": "edit",
                            "summary": "Replace exact anchor",
                            "reason": "Approved placement",
                            "dependencies": [],
                            "changes": [
                                {
                                    "path": "A.md",
                                    "replacements": [
                                        {"old": "old", "new": "new", "count": 1}
                                    ],
                                }
                            ],
                        }
                    ],
                },
            )
            rendered = run_script(
                ACTION_ENGINE,
                "render",
                "--vault",
                str(root),
                "--plan",
                str(plan_path),
                "--report",
                str(report_path),
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            report_path.write_text(
                report_path.read_text(encoding="utf-8").replace(
                    "- [ ] `R-001`", "- [x] `R-001`"
                ),
                encoding="utf-8",
            )
            note.write_text("changed by user\n", encoding="utf-8")
            applied = run_script(
                ACTION_ENGINE,
                "apply",
                "--vault",
                str(root),
                "--report",
                str(report_path),
            )
            self.assertEqual(applied.returncode, 3, applied.stderr)
            self.assertEqual(note.read_text(encoding="utf-8"), "changed by user\n")
            receipt = json.loads(
                next(root.glob("links-v1.receipt-*.json")).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(receipt["results"][0]["status"], "failed")


class NoteStatusTests(unittest.TestCase):
    def test_routes_explicit_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "inbox"
            folder.mkdir()
            (folder / "a.md").write_text(
                "---\nai_done: true\ncomplete: false\n---\n# A\n",
                encoding="utf-8",
            )
            (folder / "b.md").write_text(
                "---\nai_done: true\ncomplete: true\n"
                "archive_done: true\nlinks_done: false\n---\n# B\n",
                encoding="utf-8",
            )
            inspected = run_script(
                NOTE_STATUS,
                "--vault",
                str(root),
                "--target",
                "inbox",
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            payload = json.loads(inspected.stdout)
            stages = {item["path"]: item["next_stage"] for item in payload}
            self.assertEqual(stages["inbox/a.md"], "waiting_acceptance")
            self.assertEqual(stages["inbox/b.md"], "links")


if __name__ == "__main__":
    unittest.main()
