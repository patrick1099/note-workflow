#!/usr/bin/env python3
"""Read-only consistency checks for the note-workflow durable state.

Flags states that claim completion but are not backed by real work:
  - complete + archive_done notes still sitting at the Vault root (root is not
    a final home in archive-rules; they should have been relocated).
  - notes whose filename is a placeholder (`未命名`/`Untitled`/`N`) and that are
    not an archived original (placeholder names should have been
    preserve-and-polish renamed).
  - complete notes that never got a `kind`.

Run after a batch to catch "marked done but work not done" drift.
"""

from __future__ import annotations

import argparse
import codecs
import json
import re
import sys
from pathlib import Path
from typing import Any

DRIVE_RE = re.compile(r"^[A-Za-z]:")
SKIP_DIRS = {".git", ".obsidian", ".trash", ".note-workflow-backups"}
ORIGINAL_ARCHIVE_PARTS = ("98-Resources", "原稿归档")
STATE_KEYS = {"ai_done", "complete", "archive_done", "links_done", "kind"}
PLACEHOLDER_RE = re.compile(
    r"^(未命名( \d+)?|untitled|n)$", re.IGNORECASE
)


class StatusError(RuntimeError):
    pass


def _normalize_rel(value: str) -> str:
    value = value.strip().replace("\\", "/")
    if not value or value.startswith("/") or DRIVE_RE.match(value):
        raise StatusError(f"target 必须是 Vault 相对路径：{value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise StatusError(f"target 含非法路径段：{value}")
    return "/".join(parts)


def _decode(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig" if raw.startswith(codecs.BOM_UTF8) else "utf-8")
    except UnicodeDecodeError as exc:
        raise StatusError(f"只支持 UTF-8 Markdown：{path}") from exc


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value or value in {"null", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _frontmatter(text: str) -> dict[str, Any]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return result
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in STATE_KEYS:
            result[key] = _scalar(value)
    return result


def _is_generated_report(text: str) -> bool:
    return "<!-- note-workflow-metadata" in text


def _is_preserved_original(root: Path, path: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    prefix = tuple(part.casefold() for part in relative_parts[: len(ORIGINAL_ARCHIVE_PARTS)])
    expected = tuple(part.casefold() for part in ORIGINAL_ARCHIVE_PARTS)
    return prefix == expected


def _iter_markdown(target: Path) -> list[Path]:
    if target.is_file():
        if target.suffix.lower() != ".md":
            raise StatusError(f"target 不是 Markdown：{target}")
        return [target]
    result: list[Path] = []
    for path in target.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        result.append(path)
    return sorted(result, key=lambda item: item.as_posix().lower())


def check(root: Path, targets: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for target_value in targets:
        relative = _normalize_rel(target_value)
        target = root.joinpath(*relative.split("/")).resolve(strict=True)
        for path in _iter_markdown(target):
            if _is_preserved_original(root, path):
                continue
            text = _decode(path)
            if _is_generated_report(text):
                continue
            rel = path.relative_to(root).as_posix()
            state = _frontmatter(text)
            complete = state.get("complete") is True
            archive_done = state.get("archive_done") is True
            kind = state.get("kind")
            at_root = path.parent == root
            stem = path.stem
            placeholder = bool(PLACEHOLDER_RE.fullmatch(stem))

            if complete and archive_done and at_root:
                findings.append(
                    {
                        "path": rel,
                        "check": "root_not_archived",
                        "detail": "complete+archive_done=true 但仍位于根目录，未归位",
                    }
                )
            if placeholder and stem != "README":
                findings.append(
                    {
                        "path": rel,
                        "check": "placeholder_name",
                        "detail": "占位文件名未走 preserve-and-polish 重命名",
                    }
                )
            if complete and not kind:
                findings.append(
                    {
                        "path": rel,
                        "check": "complete_no_kind",
                        "detail": "complete=true 但缺 kind",
                    }
                )
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only consistency checks on note-workflow durable state."
    )
    parser.add_argument("--vault", required=True, help="Obsidian Vault root")
    parser.add_argument(
        "--target", action="append", required=True,
        help="Vault-relative folder or note; repeat as needed",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = Path(args.vault).resolve(strict=True)
        if not root.is_dir():
            raise StatusError(f"Vault 不是目录：{root}")
        findings = check(root, args.target)
        print(json.dumps(findings, ensure_ascii=False, indent=2))
        return 0 if not findings else 1
    except (OSError, StatusError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())