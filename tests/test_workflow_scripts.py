from __future__ import annotations

import hashlib
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
PRESERVE_ORIGINAL = PLUGIN_ROOT / "scripts" / "preserve_original.py"


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

    def test_skips_preserved_originals(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            originals = root / "98-Resources" / "原稿归档" / "inbox"
            originals.mkdir(parents=True)
            (originals / "old.md").write_text("# Old\n", encoding="utf-8")
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "new.md").write_text("# New\n", encoding="utf-8")

            inspected = run_script(
                NOTE_STATUS,
                "--vault",
                str(root),
                "--target",
                "98-Resources/原稿归档",
                "--target",
                "inbox",
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            payload = json.loads(inspected.stdout)
            self.assertEqual([item["path"] for item in payload], ["inbox/new.md"])


class ConsistencyCheckTests(unittest.TestCase):
    def test_flags_fake_done_and_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # 根目录 complete+archive_done=true 但未归位
            (root / "未命名.md").write_text(
                "---\nai_done: true\ncomplete: true\n"
                "archive_done: true\nlinks_done: true\nkind: design\n---\n# X\n",
                encoding="utf-8",
            )
            # 占位名 + 缺 kind
            (root / "未命名 1.md").write_text(
                "---\nai_done: true\ncomplete: true\n"
                "archive_done: true\nlinks_done: true\n---\n# Y\n",
                encoding="utf-8",
            )
            # 干净笔记：已归位、占位名之外、有 kind
            moved = root / "00-知识树" / "good.md"
            moved.parent.mkdir(parents=True)
            moved.write_text(
                "---\nai_done: true\ncomplete: true\n"
                "archive_done: true\nlinks_done: true\nkind: knowledge\n---\n# Good\n",
                encoding="utf-8",
            )

            checked = run_script(
                PLUGIN_ROOT / "scripts" / "consistency_check.py",
                "--vault",
                str(root),
                "--target",
                "00-知识树",
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            payload = json.loads(checked.stdout)
            self.assertEqual(payload, [])

            # 根目录不能被 normalize rel 当 target，用显式文件逐个扫
            for name in ("未命名.md", "未命名 1.md"):
                one = run_script(
                    PLUGIN_ROOT / "scripts" / "consistency_check.py",
                    "--vault",
                    str(root),
                    "--target",
                    name,
                )
                self.assertEqual(one.returncode, 1)
                payload = json.loads(one.stdout)
                self.assertEqual(payload[0]["path"], name)
                kinds = {item["check"] for item in payload}
                self.assertIn("placeholder_name", kinds)


class PreserveOriginalTests(unittest.TestCase):
    def _plan(
        self,
        root: Path,
        *,
        source: str,
        archive: str,
        target: str,
        content: str,
    ) -> Path:
        source_bytes = root.joinpath(*source.split("/")).read_bytes()
        plan_path = root / "preserve-plan.json"
        write_json(
            plan_path,
            {
                "version": 1,
                "source": source,
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "archive": archive,
                "target": target,
                "content": content,
            },
        )
        return plan_path

    def test_preserves_original_and_replaces_same_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "inbox"
            inbox.mkdir()
            source = inbox / "rough.md"
            original = b"# rough\r\nraw text\r\n"
            source.write_bytes(original)
            archive = "98-Resources/原稿归档/inbox/rough.md"
            content = (
                "# rough\n\nPolished text.\n\n---\n"
                "原稿：[[98-Resources/原稿归档/inbox/rough|rough（原稿）]]\n"
            )
            plan = self._plan(
                root,
                source="inbox/rough.md",
                archive=archive,
                target="inbox/rough.md",
                content=content,
            )

            checked = run_script(
                PRESERVE_ORIGINAL,
                "check",
                "--vault",
                str(root),
                "--plan",
                str(plan),
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(source.read_bytes(), original)

            applied = run_script(
                PRESERVE_ORIGINAL,
                "apply",
                "--vault",
                str(root),
                "--plan",
                str(plan),
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(
                root.joinpath(*archive.split("/")).read_bytes(),
                original,
            )
            self.assertEqual(source.read_text(encoding="utf-8"), content)

    def test_can_correct_title_and_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "inbox"
            inbox.mkdir()
            source = inbox / "wrong.md"
            source.write_text("# Wrong\nraw\n", encoding="utf-8")
            archive = "98-Resources/原稿归档/inbox/wrong.md"
            content = (
                "# Accurate title\n\nStructured.\n\n---\n"
                "原稿：[[98-Resources/原稿归档/inbox/wrong|wrong（原稿）]]\n"
            )
            plan = self._plan(
                root,
                source="inbox/wrong.md",
                archive=archive,
                target="inbox/Accurate title.md",
                content=content,
            )

            applied = run_script(
                PRESERVE_ORIGINAL,
                "apply",
                "--vault",
                str(root),
                "--plan",
                str(plan),
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertFalse(source.exists())
            self.assertTrue((inbox / "Accurate title.md").is_file())

    def test_rejects_missing_source_link_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "inbox"
            inbox.mkdir()
            source = inbox / "rough.md"
            original = b"# rough\nraw\n"
            source.write_bytes(original)
            plan = self._plan(
                root,
                source="inbox/rough.md",
                archive="98-Resources/原稿归档/inbox/rough.md",
                target="inbox/rough.md",
                content="# rough\n\nPolished but unlinked.\n",
            )

            applied = run_script(
                PRESERVE_ORIGINAL,
                "apply",
                "--vault",
                str(root),
                "--plan",
                str(plan),
            )
            self.assertEqual(applied.returncode, 2)
            self.assertIn("必须链接原稿", applied.stderr)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((root / "98-Resources").exists())

    def test_rejects_source_drift_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "inbox"
            inbox.mkdir()
            source = inbox / "rough.md"
            source.write_text("# rough\nraw\n", encoding="utf-8")
            archive = "98-Resources/原稿归档/inbox/rough.md"
            plan = self._plan(
                root,
                source="inbox/rough.md",
                archive=archive,
                target="inbox/rough.md",
                content=(
                    "# rough\n\nPolished.\n\n---\n"
                    "原稿：[[98-Resources/原稿归档/inbox/rough]]\n"
                ),
            )
            source.write_text("# rough\nuser changed it\n", encoding="utf-8")

            applied = run_script(
                PRESERVE_ORIGINAL,
                "apply",
                "--vault",
                str(root),
                "--plan",
                str(plan),
            )
            self.assertEqual(applied.returncode, 2)
            self.assertIn("原稿已变化", applied.stderr)
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "# rough\nuser changed it\n",
            )
            self.assertFalse(root.joinpath(*archive.split("/")).exists())

    def test_rejects_windows_reserved_target_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "inbox"
            inbox.mkdir()
            source = inbox / "rough.md"
            original = b"# rough\nraw\n"
            source.write_bytes(original)
            plan = self._plan(
                root,
                source="inbox/rough.md",
                archive="98-Resources/原稿归档/inbox/rough.md",
                target="inbox/CON.md",
                content=(
                    "# CON\n\nPolished.\n\n---\n"
                    "原稿：[[98-Resources/原稿归档/inbox/rough]]\n"
                ),
            )

            applied = run_script(
                PRESERVE_ORIGINAL,
                "apply",
                "--vault",
                str(root),
                "--plan",
                str(plan),
            )
            self.assertEqual(applied.returncode, 2)
            self.assertIn("Windows 保留名", applied.stderr)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
