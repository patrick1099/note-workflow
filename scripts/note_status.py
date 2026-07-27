#!/usr/bin/env python3
"""Inspect durable note-workflow state in explicitly selected Vault paths."""

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
STATE_KEYS = {
    "ai_done",
    "complete",
    "archive_done",
    "links_done",
    "ai_question",
    "ai_feedback",
    "kind",
}


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


def _resolve(root: Path, value: str) -> tuple[str, Path]:
    relative = _normalize_rel(value)
    path = root.joinpath(*relative.split("/")).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise StatusError(f"target 逃逸 Vault：{relative}") from exc
    return relative, path


def _decode(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode(
            "utf-8-sig" if raw.startswith(codecs.BOM_UTF8) else "utf-8"
        )
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


def _next_stage(state: dict[str, Any]) -> str:
    if state.get("ai_question"):
        return "waiting_question"
    if state.get("ai_done") is not True:
        return "organize"
    if state.get("complete") is not True:
        return "waiting_acceptance"
    if state.get("archive_done") is not True:
        return "archive"
    if state.get("links_done") is not True:
        return "links"
    return "complete"


def _is_generated_report(text: str) -> bool:
    return "<!-- note-workflow-metadata" in text


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


def _is_preserved_original(root: Path, path: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    prefix = tuple(
        part.casefold() for part in relative_parts[: len(ORIGINAL_ARCHIVE_PARTS)]
    )
    expected = tuple(part.casefold() for part in ORIGINAL_ARCHIVE_PARTS)
    return prefix == expected


def inspect(root: Path, targets: list[str]) -> list[dict[str, Any]]:
    notes: dict[str, dict[str, Any]] = {}
    for target_value in targets:
        relative, target = _resolve(root, target_value)
        if target == root:
            raise StatusError("不得默认扫描整个 Vault；请指定笔记或子文件夹")
        for path in _iter_markdown(target):
            if _is_preserved_original(root, path):
                continue
            text = _decode(path)
            if _is_generated_report(text):
                continue
            path_relative = path.relative_to(root).as_posix()
            state = _frontmatter(text)
            item = {
                "path": path_relative,
                "ai_done": state.get("ai_done") is True,
                "complete": state.get("complete") is True,
                "archive_done": state.get("archive_done") is True,
                "links_done": state.get("links_done") is True,
                "ai_question": state.get("ai_question"),
                "ai_feedback": state.get("ai_feedback"),
                "kind": state.get("kind"),
            }
            item["next_stage"] = _next_stage(item)
            notes[path_relative] = item
    return [notes[key] for key in sorted(notes, key=str.lower)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect note-workflow state in explicit Obsidian paths."
    )
    parser.add_argument("--vault", required=True, help="Obsidian Vault root")
    parser.add_argument(
        "--target",
        action="append",
        required=True,
        help="Vault-relative Markdown file or subfolder; repeat as needed",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = Path(args.vault).resolve(strict=True)
        if not root.is_dir():
            raise StatusError(f"Vault 不是目录：{root}")
        print(json.dumps(inspect(root, args.target), ensure_ascii=False, indent=2))
        return 0
    except (OSError, StatusError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
