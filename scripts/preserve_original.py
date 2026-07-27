#!/usr/bin/env python3
"""Replace a note with a polished version while preserving the original bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


ARCHIVE_ROOT = "98-Resources/原稿归档"
DRIVE_RE = re.compile(r"^[A-Za-z]:")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
WINDOWS_RESERVED_RE = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)


class PreserveError(RuntimeError):
    """Raised when an original-preservation plan is invalid or unsafe."""


def _normalize_rel(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreserveError(f"{field} 必须是非空 Vault 相对路径")
    value = value.strip().replace("\\", "/")
    if value.startswith("/") or DRIVE_RE.match(value):
        raise PreserveError(f"{field} 不得使用绝对路径：{value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PreserveError(f"{field} 含非法路径段：{value}")
    return "/".join(parts)


def _resolve(root: Path, value: Any, field: str) -> tuple[str, Path]:
    relative = _normalize_rel(value, field)
    path = root.joinpath(*relative.split("/")).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PreserveError(f"{field} 逃逸 Vault：{relative}") from exc
    return relative, path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_plan(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreserveError(f"无法读取计划：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreserveError("计划根节点必须是对象")
    return value


def _wikilink_targets(content: str) -> set[str]:
    targets: set[str] = set()
    for match in WIKILINK_RE.finditer(content):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if target.endswith(".md"):
            target = target[:-3]
        if target:
            targets.add(target.replace("\\", "/"))
    return targets


def _last_nonempty_line(content: str) -> str:
    for line in reversed(content.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _validate_target_filename(name: str) -> None:
    if any(character in name for character in '<>:"/\\|?*'):
        raise PreserveError(f"润色版文件名含 Windows 非法字符：{name}")
    if name.endswith((" ", ".")):
        raise PreserveError(f"润色版文件名不得以空格或句点结尾：{name}")
    if WINDOWS_RESERVED_RE.fullmatch(Path(name).stem):
        raise PreserveError(f"润色版文件名是 Windows 保留名：{name}")


def _atomic_write(path: Path, data: bytes) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".note-workflow.tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()


def _validate(
    root: Path, plan: dict[str, Any]
) -> tuple[dict[str, Any], Path, Path, Path, bytes]:
    if plan.get("version") != 1:
        raise PreserveError("计划 version 必须为 1")

    source_rel, source = _resolve(root, plan.get("source"), "source")
    archive_rel, archive = _resolve(root, plan.get("archive"), "archive")
    target_rel, target = _resolve(root, plan.get("target"), "target")

    if not source_rel.lower().endswith(".md"):
        raise PreserveError("source 必须是 Markdown 文件")
    if not archive_rel.lower().endswith(".md"):
        raise PreserveError("archive 必须是 Markdown 文件")
    if not target_rel.lower().endswith(".md"):
        raise PreserveError("target 必须是 Markdown 文件")
    _validate_target_filename(target.name)
    if source_rel == archive_rel or target_rel == archive_rel:
        raise PreserveError("source、archive、target 路径不得冲突")
    if source_rel == ARCHIVE_ROOT or source_rel.startswith(f"{ARCHIVE_ROOT}/"):
        raise PreserveError("原稿归档目录中的文件不得再次生成润色版")
    if not archive_rel.startswith(f"{ARCHIVE_ROOT}/"):
        raise PreserveError(f"archive 必须位于 {ARCHIVE_ROOT}/")
    if source.parent != target.parent:
        raise PreserveError("润色版必须留在原稿原目录")
    if not source.is_file():
        raise PreserveError(f"原稿不存在：{source_rel}")
    if archive.exists():
        raise PreserveError(f"原稿归档目标已存在：{archive_rel}")
    if target != source and target.exists():
        raise PreserveError(f"润色版目标已存在：{target_rel}")

    source_bytes = source.read_bytes()
    expected_hash = plan.get("source_sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", expected_hash
    ):
        raise PreserveError("source_sha256 必须是 64 位十六进制 SHA256")
    actual_hash = _sha256(source_bytes)
    if actual_hash.lower() != expected_hash.lower():
        raise PreserveError("原稿已变化；请重新读取并生成计划")

    content = plan.get("content")
    if not isinstance(content, str) or not content.strip():
        raise PreserveError("content 必须是非空润色版 Markdown")
    archive_link = archive_rel[:-3]
    if archive_link not in _wikilink_targets(content):
        raise PreserveError(f"润色版结尾必须链接原稿：[[{archive_link}]]")
    if archive_link not in _wikilink_targets(_last_nonempty_line(content)):
        raise PreserveError("润色版最后一个非空行必须是原稿链接")

    h1_match = H1_RE.search(content)
    if h1_match and h1_match.group(1).strip() != target.stem:
        raise PreserveError("润色版首个一级标题必须与目标文件名一致")

    normalized = {
        "version": 1,
        "source": source_rel,
        "archive": archive_rel,
        "target": target_rel,
        "source_sha256": actual_hash,
        "content": content,
    }
    return normalized, source, archive, target, source_bytes


def _execute(root: Path, plan: dict[str, Any], *, write: bool) -> dict[str, Any]:
    normalized, source, archive, target, source_bytes = _validate(root, plan)
    result = {
        "mode": "apply" if write else "check",
        "source": normalized["source"],
        "archive": normalized["archive"],
        "target": normalized["target"],
        "source_sha256": normalized["source_sha256"],
        "original_bytes_preserved": True,
    }
    if not write:
        return result

    archive.parent.mkdir(parents=True, exist_ok=True)
    moved = False
    target_created = False
    try:
        os.replace(source, archive)
        moved = True
        _atomic_write(target, normalized["content"].encode("utf-8"))
        target_created = True
        if archive.read_bytes() != source_bytes:
            raise PreserveError("原稿归档后的字节校验失败")
    except Exception as exc:
        rollback_error: Exception | None = None
        try:
            if target_created and target.exists():
                target.unlink()
            if moved and archive.exists() and not source.exists():
                os.replace(archive, source)
        except Exception as rollback_exc:
            rollback_error = rollback_exc
        if rollback_error is not None:
            raise PreserveError(
                f"写入失败且回滚失败：{exc}; 回滚错误：{rollback_error}"
            ) from exc
        raise PreserveError(f"写入失败，已恢复原稿：{exc}") from exc

    result["applied"] = True
    return result


def _command(args: argparse.Namespace, *, write: bool) -> int:
    root = Path(args.vault).resolve(strict=True)
    if not root.is_dir():
        raise PreserveError(f"Vault 不是目录：{root}")
    plan = _read_plan(Path(args.plan))
    result = _execute(root, plan, write=write)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preserve an original note and create its polished replacement."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, write in (("check", False), ("apply", True)):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--vault", required=True)
        command_parser.add_argument("--plan", required=True)
        command_parser.set_defaults(
            func=lambda args, should_write=write: _command(
                args, write=should_write
            )
        )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (OSError, PreserveError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
