#!/usr/bin/env python3
"""Render and apply exact, human-approved Obsidian note actions."""

from __future__ import annotations

import argparse
import base64
import codecs
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class PlanError(RuntimeError):
    """Raised when a plan, report, or current filesystem state is unsafe."""


ACTION_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d{3,}$")
BOX_RE = re.compile(r"^- \[([ xX])\] `([^`]+)`\s*$", re.MULTILINE)
SUGGESTION_RE = re.compile(r"^(\s*- 建议：).*$", re.MULTILINE)
METADATA_RE = re.compile(
    r"<!-- note-workflow-metadata\n(?P<data>\{.*?\})\n-->\s*",
    re.DOTALL,
)
DRIVE_RE = re.compile(r"^[A-Za-z]:")
ARCHIVE_TYPES = {"mkdir", "move", "decision"}
LINK_TYPES = {"edit", "decision"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"无法读取 JSON：{path}: {exc}") from exc


def _read_utf8(path: Path) -> tuple[str, bool, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlanError(f"无法读取文件：{path}: {exc}") from exc
    has_bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text = raw.decode("utf-8-sig" if has_bom else "utf-8")
    except UnicodeDecodeError as exc:
        raise PlanError(f"只支持 UTF-8 Markdown：{path}") from exc
    return text, has_bom, raw


def _encode_utf8(text: str, has_bom: bool) -> bytes:
    encoded = text.encode("utf-8")
    return codecs.BOM_UTF8 + encoded if has_bom else encoded


def _atomic_write(path: Path, data: bytes, *, write: bool) -> None:
    """The single write gate for generated and edited files."""
    if not write:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _mkdir(path: Path, *, write: bool) -> None:
    """The single write gate for planned directory creation."""
    if not write:
        return
    path.mkdir()


def _move(source: Path, target: Path, *, write: bool) -> None:
    """The single write gate for planned moves."""
    if not write:
        return
    shutil.move(str(source), str(target))


def _normalize_rel(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{field} 必须是非空 Vault 相对路径")
    value = value.strip().replace("\\", "/")
    if value.startswith("/") or DRIVE_RE.match(value):
        raise PlanError(f"{field} 不得使用绝对路径：{value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PlanError(f"{field} 含非法路径段：{value}")
    return "/".join(parts)


def _resolve(root: Path, value: Any, field: str) -> tuple[str, Path]:
    rel = _normalize_rel(value, field)
    candidate = root.joinpath(*rel.split("/"))
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PlanError(f"{field} 逃逸 Vault：{rel}") from exc
    return rel, resolved


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{field} 必须是非空字符串")
    return value.strip()


def _validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise PlanError("计划根节点必须是对象")
    result = copy.deepcopy(plan)
    if result.get("version") != 1:
        raise PlanError("计划 version 必须为 1")
    stage = result.get("stage")
    if stage not in {"archive", "links"}:
        raise PlanError("计划 stage 必须是 archive 或 links")
    result["title"] = _required_string(result.get("title"), "title")
    actions = result.get("actions")
    if not isinstance(actions, list) or not actions:
        raise PlanError("计划必须至少包含一个动作；无变更时使用 decision")

    allowed = ARCHIVE_TYPES if stage == "archive" else LINK_TYPES
    ids: set[str] = set()
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise PlanError(f"actions[{index}] 必须是对象")
        action_id = _required_string(action.get("id"), f"actions[{index}].id")
        if not ACTION_ID_RE.fullmatch(action_id):
            raise PlanError(f"动作 ID 格式错误：{action_id}")
        if action_id in ids:
            raise PlanError(f"动作 ID 重复：{action_id}")
        ids.add(action_id)
        action_type = action.get("type")
        if action_type not in allowed:
            raise PlanError(f"{stage} 阶段不允许动作 {action_type!r}")
        action["summary"] = _required_string(
            action.get("summary"), f"{action_id}.summary"
        )
        action["reason"] = _required_string(
            action.get("reason"), f"{action_id}.reason"
        )
        dependencies = action.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(item, str) for item in dependencies
        ):
            raise PlanError(f"{action_id}.dependencies 必须是字符串数组")
        if len(dependencies) != len(set(dependencies)):
            raise PlanError(f"{action_id}.dependencies 含重复 ID")
        if action_id in dependencies:
            raise PlanError(f"{action_id} 不得依赖自身")
        action["dependencies"] = dependencies

    for action in actions:
        unknown = set(action["dependencies"]) - ids
        if unknown:
            raise PlanError(
                f"{action['id']} 依赖不存在的动作：{', '.join(sorted(unknown))}"
            )

    _topological_ids({item["id"]: item for item in actions}, ids)
    _validate_unique_archive_paths(result)
    return result


def _validate_unique_archive_paths(plan: dict[str, Any]) -> None:
    if plan["stage"] != "archive":
        return
    mkdir_paths: set[str] = set()
    move_sources: set[str] = set()
    move_targets: set[str] = set()
    for action in plan["actions"]:
        if action["type"] == "mkdir":
            rel = _normalize_rel(action.get("path"), f"{action['id']}.path")
            if rel in mkdir_paths:
                raise PlanError(f"重复创建目录：{rel}")
            mkdir_paths.add(rel)
        elif action["type"] == "move":
            source = _normalize_rel(action.get("source"), f"{action['id']}.source")
            target = _normalize_rel(action.get("target"), f"{action['id']}.target")
            if source in move_sources:
                raise PlanError(f"多个动作移动同一源文件：{source}")
            if target in move_targets:
                raise PlanError(f"多个动作写入同一目标：{target}")
            move_sources.add(source)
            move_targets.add(target)


def _topological_ids(
    action_map: dict[str, dict[str, Any]], selected: set[str]
) -> list[str]:
    order: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(action_id: str) -> None:
        if action_id in visited:
            return
        if action_id in visiting:
            raise PlanError(f"动作依赖形成循环：{action_id}")
        visiting.add(action_id)
        for dependency in action_map[action_id].get("dependencies", []):
            if dependency in selected:
                visit(dependency)
        visiting.remove(action_id)
        visited.add(action_id)
        order.append(action_id)

    for action_id in action_map:
        if action_id in selected:
            visit(action_id)
    return order


def _planned_mkdirs(
    root: Path, actions: list[dict[str, Any]]
) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for action in actions:
        if action["type"] != "mkdir":
            continue
        rel, path = _resolve(root, action.get("path"), f"{action['id']}.path")
        action["path"] = rel
        result[path] = action["id"]
    return result


def _validate_parent(
    path: Path,
    action: dict[str, Any],
    planned_dirs: dict[Path, str],
    field: str,
) -> None:
    parent = path.parent
    if parent.exists():
        if not parent.is_dir():
            raise PlanError(f"{field} 的父路径不是目录：{parent}")
        return
    dependency = planned_dirs.get(parent)
    if dependency is None or dependency not in action["dependencies"]:
        raise PlanError(
            f"{action['id']} 的父目录不存在，且没有依赖对应 mkdir 动作：{parent}"
        )


def _enrich_archive(plan: dict[str, Any], root: Path) -> None:
    planned_dirs = _planned_mkdirs(root, plan["actions"])
    for action in plan["actions"]:
        action_type = action["type"]
        if action_type == "decision":
            continue
        if action_type == "mkdir":
            rel, path = _resolve(root, action["path"], f"{action['id']}.path")
            action["path"] = rel
            if path.exists():
                raise PlanError(f"{action['id']} 的目录已经存在：{rel}")
            _validate_parent(path, action, planned_dirs, f"{action['id']}.path")
            _mkdir(path, write=False)
            continue

        source_rel, source = _resolve(
            root, action.get("source"), f"{action['id']}.source"
        )
        target_rel, target = _resolve(
            root, action.get("target"), f"{action['id']}.target"
        )
        action["source"] = source_rel
        action["target"] = target_rel
        if source == target:
            raise PlanError(f"{action['id']} 的源和目标相同")
        if not source.is_file():
            raise PlanError(f"{action['id']} 的源文件不存在：{source_rel}")
        if target.exists():
            raise PlanError(f"{action['id']} 的目标已存在：{target_rel}")
        _validate_parent(target, action, planned_dirs, f"{action['id']}.target")
        action["source_sha256"] = _sha256(source.read_bytes())
        _move(source, target, write=False)


def _apply_replacements(
    text: str, replacements: list[dict[str, Any]], action_id: str
) -> str:
    for index, replacement in enumerate(replacements):
        if not isinstance(replacement, dict):
            raise PlanError(f"{action_id}.replacements[{index}] 必须是对象")
        old = replacement.get("old")
        new = replacement.get("new")
        count = replacement.get("count", 1)
        if not isinstance(old, str) or not old:
            raise PlanError(f"{action_id} 的 old 不得为空")
        if not isinstance(new, str):
            raise PlanError(f"{action_id} 的 new 必须是字符串")
        if old == new:
            raise PlanError(f"{action_id} 的 old 与 new 相同")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise PlanError(f"{action_id} 的 count 必须是正整数")
        actual = text.count(old)
        if actual != count:
            raise PlanError(
                f"{action_id} 的锚点匹配 {actual} 次，计划要求 {count} 次"
            )
        replacement["count"] = count
        text = text.replace(old, new, count)
    return text


def _enrich_links(plan: dict[str, Any], root: Path) -> None:
    for action in plan["actions"]:
        if action["type"] == "decision":
            continue
        changes = action.get("changes")
        if not isinstance(changes, list) or not changes:
            raise PlanError(f"{action['id']}.changes 必须是非空数组")
        seen: set[str] = set()
        for index, change in enumerate(changes):
            if not isinstance(change, dict):
                raise PlanError(f"{action['id']}.changes[{index}] 必须是对象")
            rel, path = _resolve(
                root, change.get("path"), f"{action['id']}.changes[{index}].path"
            )
            if rel in seen:
                raise PlanError(f"{action['id']} 重复修改同一文件：{rel}")
            seen.add(rel)
            if not path.is_file():
                raise PlanError(f"{action['id']} 的文件不存在：{rel}")
            text, _, raw = _read_utf8(path)
            replacements = change.get("replacements")
            if not isinstance(replacements, list) or not replacements:
                raise PlanError(f"{action['id']} 的 replacements 必须是非空数组")
            result = _apply_replacements(text, replacements, action["id"])
            change["path"] = rel
            change["snapshot_sha256"] = _sha256(raw)
            change["result_sha256"] = _sha256(result.encode("utf-8"))
            _atomic_write(path, result.encode("utf-8"), write=False)


def _enrich_plan(plan: dict[str, Any], root: Path) -> dict[str, Any]:
    result = _validate_plan(plan)
    if result["stage"] == "archive":
        _enrich_archive(result, root)
    else:
        _enrich_links(result, root)
    result["generated_at"] = _now()
    return result


def _max_backtick_run(text: str) -> int:
    return max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)


def _fenced(text: str, indent: str = "    ") -> list[str]:
    fence = "`" * max(3, _max_backtick_run(text) + 1)
    lines = [f"{indent}{fence}text"]
    lines.extend(f"{indent}{line}" for line in text.split("\n"))
    lines.append(f"{indent}{fence}")
    return lines


def _render_action(action: dict[str, Any]) -> list[str]:
    lines = [
        f"- [ ] `{action['id']}`",
        f"  - 操作：{action['summary']}",
        f"  - 类型：`{action['type']}`",
    ]
    dependencies = action.get("dependencies", [])
    lines.append(
        "  - 依赖：" + (", ".join(f"`{item}`" for item in dependencies) or "无")
    )
    if action["type"] == "mkdir":
        lines.append(f"  - 路径：`{action['path']}`")
    elif action["type"] == "move":
        lines.extend(
            [
                f"  - 原路径：`{action['source']}`",
                f"  - 目标路径：`{action['target']}`",
                f"  - 源文件 SHA-256：`{action['source_sha256']}`",
            ]
        )
    elif action["type"] == "edit":
        if action.get("relation"):
            lines.append(f"  - 关系：{action['relation']}")
        lines.append("  - 将修改：")
        for change in action["changes"]:
            lines.append(f"    - 文件：`{change['path']}`")
            lines.append(f"      - 快照 SHA-256：`{change['snapshot_sha256']}`")
            for replacement in change["replacements"]:
                lines.append("      - 修改前：")
                lines.extend(_fenced(replacement["old"], "        "))
                lines.append("      - 修改后：")
                lines.extend(_fenced(replacement["new"], "        "))
    lines.extend(
        [
            f"  - 原因：{action['reason']}",
            "  - 建议：",
            "",
        ]
    )
    return lines


def _visible_report(plan: dict[str, Any]) -> str:
    stage_name = "归档" if plan["stage"] == "archive" else "链接"
    lines = [
        f"# {plan['title']}",
        "",
        f"生成时间：{plan['generated_at']}",
        "状态：等待用户审批",
        f"阶段：{stage_name}",
        "",
        "> 只勾选你同意的动作；不同意时保持未勾选并在“建议”后填写文字。",
        "> 除复选框和单行“建议”外，不要修改报告中的动作正文。",
        "",
        "## 操作",
        "",
    ]
    for action in plan["actions"]:
        lines.extend(_render_action(action))
    return "\n".join(lines).rstrip() + "\n"


def _without_metadata(report_text: str) -> str:
    return METADATA_RE.sub("", report_text)


def _protected_text(report_text: str) -> str:
    text = _without_metadata(report_text).replace("\r\n", "\n").replace("\r", "\n")
    text = BOX_RE.sub(lambda match: f"- [ ] `{match.group(2)}`", text)
    text = SUGGESTION_RE.sub(lambda match: match.group(1), text)
    return text


def _attach_metadata(visible: str, plan: dict[str, Any]) -> str:
    plan_bytes = _canonical_json(plan)
    metadata = {
        "plan_sha256": _sha256(plan_bytes),
        "protected_sha256": _sha256(_protected_text(visible).encode("utf-8")),
        "plan_base64": base64.b64encode(plan_bytes).decode("ascii"),
    }
    payload = json.dumps(metadata, ensure_ascii=True, sort_keys=True)
    return visible + f"<!-- note-workflow-metadata\n{payload}\n-->\n"


def _extract_report(report_path: Path) -> tuple[dict[str, Any], dict[str, bool], str]:
    try:
        report_text = report_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise PlanError(f"无法读取报告：{report_path}: {exc}") from exc
    matches = list(METADATA_RE.finditer(report_text))
    if len(matches) != 1:
        raise PlanError("报告必须且只能包含一个 note-workflow metadata 块")
    try:
        metadata = json.loads(matches[0].group("data"))
        plan_bytes = base64.b64decode(metadata["plan_base64"], validate=True)
        plan = json.loads(plan_bytes.decode("utf-8"))
    except (KeyError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError("报告内嵌计划损坏") from exc
    if _sha256(plan_bytes) != metadata.get("plan_sha256"):
        raise PlanError("报告内嵌计划哈希不匹配")
    protected = _sha256(_protected_text(report_text).encode("utf-8"))
    if protected != metadata.get("protected_sha256"):
        raise PlanError("报告受保护正文已变化；必须重新生成 Dry Run")

    approvals: dict[str, bool] = {}
    for match in BOX_RE.finditer(report_text):
        action_id = match.group(2)
        if action_id in approvals:
            raise PlanError(f"报告中动作 ID 重复：{action_id}")
        approvals[action_id] = match.group(1).lower() == "x"
    plan = _validate_plan(plan)
    expected = {action["id"] for action in plan["actions"]}
    if set(approvals) != expected:
        missing = expected - set(approvals)
        unknown = set(approvals) - expected
        raise PlanError(
            "报告复选框与计划不一致"
            f"；缺少={sorted(missing)}，未知={sorted(unknown)}"
        )
    return plan, approvals, metadata["plan_sha256"]


def _copy_backup(root: Path, relative: str, backup_root: Path) -> None:
    _, source = _resolve(root, relative, "backup.path")
    target = backup_root.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _backup_root(root: Path, report: Path) -> Path:
    safe_report = re.sub(r"[^A-Za-z0-9._-]+", "-", report.stem).strip("-")
    safe_report = safe_report or "report"
    return root / ".note-workflow-backups" / safe_report / _stamp()


def _initial_results(
    plan: dict[str, Any], approvals: dict[str, bool]
) -> dict[str, dict[str, str]]:
    return {
        action["id"]: {
            "id": action["id"],
            "status": "selected" if approvals[action["id"]] else "pending",
            "detail": "等待执行" if approvals[action["id"]] else "用户未勾选",
        }
        for action in plan["actions"]
    }


def _mark_dependency_blocks(
    action_map: dict[str, dict[str, Any]],
    order: list[str],
    selected: set[str],
    results: dict[str, dict[str, str]],
) -> None:
    changed = True
    while changed:
        changed = False
        for action_id in order:
            if results[action_id]["status"] not in {"selected", "valid"}:
                continue
            for dependency in action_map[action_id]["dependencies"]:
                if dependency not in selected:
                    results[action_id] = {
                        "id": action_id,
                        "status": "blocked",
                        "detail": f"依赖 {dependency} 未勾选",
                    }
                    changed = True
                    break
                if results[dependency]["status"] in {"failed", "blocked"}:
                    results[action_id] = {
                        "id": action_id,
                        "status": "blocked",
                        "detail": f"依赖 {dependency} 未通过",
                    }
                    changed = True
                    break


def _preflight_archive_action(
    root: Path,
    action: dict[str, Any],
    planned_dirs: dict[Path, str],
) -> None:
    action_type = action["type"]
    if action_type == "decision":
        return
    if action_type == "mkdir":
        _, path = _resolve(root, action["path"], f"{action['id']}.path")
        if path.exists():
            raise PlanError(f"目录状态已变化：{action['path']}")
        _validate_parent(path, action, planned_dirs, f"{action['id']}.path")
        _mkdir(path, write=False)
        return
    _, source = _resolve(root, action["source"], f"{action['id']}.source")
    _, target = _resolve(root, action["target"], f"{action['id']}.target")
    if not source.is_file():
        raise PlanError(f"源文件不存在：{action['source']}")
    if _sha256(source.read_bytes()) != action.get("source_sha256"):
        raise PlanError(f"源文件已变化：{action['source']}")
    if target.exists():
        raise PlanError(f"目标已经存在：{action['target']}")
    _validate_parent(target, action, planned_dirs, f"{action['id']}.target")
    _move(source, target, write=False)


def _apply_archive(
    root: Path,
    plan: dict[str, Any],
    approvals: dict[str, bool],
    report: Path,
) -> tuple[dict[str, dict[str, str]], str | None]:
    action_map = {action["id"]: action for action in plan["actions"]}
    selected = {action_id for action_id, checked in approvals.items() if checked}
    order = _topological_ids(action_map, selected)
    results = _initial_results(plan, approvals)
    selected_actions = [action_map[action_id] for action_id in order]
    planned_dirs = _planned_mkdirs(root, selected_actions)

    for action_id in order:
        try:
            _preflight_archive_action(root, action_map[action_id], planned_dirs)
            results[action_id] = {
                "id": action_id,
                "status": "valid",
                "detail": "预检通过",
            }
        except PlanError as exc:
            results[action_id] = {
                "id": action_id,
                "status": "failed",
                "detail": str(exc),
            }
    _mark_dependency_blocks(action_map, order, selected, results)
    ready = [
        action_id for action_id in order if results[action_id]["status"] == "valid"
    ]
    if not ready:
        return results, None

    files_to_backup = [
        action_map[action_id]["source"]
        for action_id in ready
        if action_map[action_id]["type"] == "move"
    ]
    backup_root = _backup_root(root, report) if files_to_backup else None
    if backup_root:
        for relative in files_to_backup:
            _copy_backup(root, relative, backup_root)

    created_dirs: list[Path] = []
    moved: list[tuple[Path, Path]] = []
    try:
        for action_id in ready:
            action = action_map[action_id]
            if action["type"] == "decision":
                results[action_id] = {
                    "id": action_id,
                    "status": "executed",
                    "detail": "决定已确认，无文件写入",
                }
            elif action["type"] == "mkdir":
                _, path = _resolve(root, action["path"], f"{action_id}.path")
                _mkdir(path, write=True)
                created_dirs.append(path)
                results[action_id] = {
                    "id": action_id,
                    "status": "executed",
                    "detail": f"已创建 {action['path']}",
                }
            else:
                _, source = _resolve(root, action["source"], f"{action_id}.source")
                _, target = _resolve(root, action["target"], f"{action_id}.target")
                _move(source, target, write=True)
                moved.append((source, target))
                results[action_id] = {
                    "id": action_id,
                    "status": "executed",
                    "detail": f"已移动到 {action['target']}",
                }
    except Exception as exc:
        for source, target in reversed(moved):
            if target.exists() and not source.exists():
                shutil.move(str(target), str(source))
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        for action_id in ready:
            if results[action_id]["status"] == "executed":
                results[action_id] = {
                    "id": action_id,
                    "status": "rolled_back",
                    "detail": f"批次失败并回滚：{exc}",
                }
        raise PlanError(f"归档写入失败，已尝试回滚：{exc}") from exc
    return results, str(backup_root.relative_to(root).as_posix()) if backup_root else None


def _preflight_link_action(root: Path, action: dict[str, Any]) -> None:
    if action["type"] == "decision":
        return
    for change in action["changes"]:
        _, path = _resolve(root, change["path"], f"{action['id']}.path")
        if not path.is_file():
            raise PlanError(f"文件不存在：{change['path']}")
        text, _, raw = _read_utf8(path)
        if _sha256(raw) != change.get("snapshot_sha256"):
            raise PlanError(f"文件已变化：{change['path']}")
        _apply_replacements(text, copy.deepcopy(change["replacements"]), action["id"])


def _apply_links(
    root: Path,
    plan: dict[str, Any],
    approvals: dict[str, bool],
    report: Path,
) -> tuple[dict[str, dict[str, str]], str | None]:
    action_map = {action["id"]: action for action in plan["actions"]}
    selected = {action_id for action_id, checked in approvals.items() if checked}
    order = _topological_ids(action_map, selected)
    results = _initial_results(plan, approvals)

    for action_id in order:
        try:
            _preflight_link_action(root, action_map[action_id])
            results[action_id] = {
                "id": action_id,
                "status": "valid",
                "detail": "预检通过",
            }
        except PlanError as exc:
            results[action_id] = {
                "id": action_id,
                "status": "failed",
                "detail": str(exc),
            }
    _mark_dependency_blocks(action_map, order, selected, results)

    virtual: dict[str, tuple[str, bool]] = {}
    successful_edits: list[str] = []
    successful_decisions: list[str] = []
    for action_id in order:
        if results[action_id]["status"] != "valid":
            continue
        action = action_map[action_id]
        if any(
            results[dependency]["status"] not in {"executed", "valid", "prepared"}
            for dependency in action["dependencies"]
        ):
            results[action_id] = {
                "id": action_id,
                "status": "blocked",
                "detail": "依赖动作没有成功",
            }
            continue
        if action["type"] == "decision":
            successful_decisions.append(action_id)
            results[action_id] = {
                "id": action_id,
                "status": "executed",
                "detail": "决定已确认，无文件写入",
            }
            continue

        local = dict(virtual)
        try:
            for change in action["changes"]:
                relative = change["path"]
                if relative in local:
                    text, has_bom = local[relative]
                else:
                    _, path = _resolve(root, relative, f"{action_id}.path")
                    text, has_bom, _ = _read_utf8(path)
                text = _apply_replacements(
                    text, copy.deepcopy(change["replacements"]), action_id
                )
                local[relative] = (text, has_bom)
        except PlanError as exc:
            results[action_id] = {
                "id": action_id,
                "status": "failed",
                "detail": f"与同批其他动作冲突：{exc}",
            }
            continue
        virtual = local
        successful_edits.append(action_id)
        results[action_id] = {
            "id": action_id,
            "status": "prepared",
            "detail": "组合变更已准备",
        }

    if not virtual:
        return results, None

    backup_root = _backup_root(root, report)
    for relative in virtual:
        _copy_backup(root, relative, backup_root)

    try:
        for relative, (text, has_bom) in virtual.items():
            _, path = _resolve(root, relative, "edit.path")
            _atomic_write(path, _encode_utf8(text, has_bom), write=True)
        for action_id in successful_edits:
            results[action_id] = {
                "id": action_id,
                "status": "executed",
                "detail": "精确文本修改已写入",
            }
    except Exception as exc:
        for relative in virtual:
            _, path = _resolve(root, relative, "rollback.path")
            backup = backup_root.joinpath(*relative.split("/"))
            if backup.is_file():
                shutil.copy2(backup, path)
        for action_id in successful_edits:
            results[action_id] = {
                "id": action_id,
                "status": "rolled_back",
                "detail": f"批次失败并回滚：{exc}",
            }
        raise PlanError(f"链接写入失败，已从备份恢复：{exc}") from exc
    return results, str(backup_root.relative_to(root).as_posix())


def _write_receipt(
    report: Path,
    plan: dict[str, Any],
    plan_sha256: str,
    results: dict[str, dict[str, str]],
    backup_dir: str | None,
) -> tuple[Path, dict[str, Any]]:
    receipt = {
        "version": 1,
        "stage": plan["stage"],
        "report": str(report),
        "plan_sha256": plan_sha256,
        "executed_at": _now(),
        "backup_dir": backup_dir,
        "results": [results[action["id"]] for action in plan["actions"]],
    }
    receipt_path = report.with_name(
        f"{report.stem}.receipt-{_stamp()}.json"
    )
    if receipt_path.exists():
        raise PlanError(f"回执文件已存在：{receipt_path}")
    _atomic_write(receipt_path, json.dumps(
        receipt, ensure_ascii=False, indent=2
    ).encode("utf-8") + b"\n", write=True)
    return receipt_path, receipt


def command_render(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve(strict=True)
    if not root.is_dir():
        raise PlanError(f"Vault 不是目录：{root}")
    plan_path = Path(args.plan).resolve(strict=True)
    report_path = Path(args.report).resolve(strict=False)
    if report_path.exists():
        raise PlanError(f"报告已存在；请使用新版本文件名：{report_path}")
    plan = _enrich_plan(_read_json(plan_path), root)
    report = _attach_metadata(_visible_report(plan), plan)
    _atomic_write(report_path, report.encode("utf-8"), write=True)
    print(
        json.dumps(
            {
                "status": "rendered",
                "report": str(report_path),
                "actions": [action["id"] for action in plan["actions"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_apply(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve(strict=True)
    if not root.is_dir():
        raise PlanError(f"Vault 不是目录：{root}")
    report = Path(args.report).resolve(strict=True)
    plan, approvals, plan_sha256 = _extract_report(report)
    if plan["stage"] == "archive":
        results, backup_dir = _apply_archive(root, plan, approvals, report)
    else:
        results, backup_dir = _apply_links(root, plan, approvals, report)
    receipt_path, receipt = _write_receipt(
        report, plan, plan_sha256, results, backup_dir
    )
    output = {
        "status": "applied",
        "receipt": str(receipt_path),
        **receipt,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    failed = any(
        item["status"] in {"failed", "blocked", "rolled_back"}
        for item in receipt["results"]
        if approvals[item["id"]]
    )
    return 3 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render and apply exact Obsidian note workflow actions."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render", help="Render a protected Dry Run report")
    render.add_argument("--vault", required=True, help="Obsidian Vault root")
    render.add_argument("--plan", required=True, help="UTF-8 JSON plan")
    render.add_argument("--report", required=True, help="New Markdown report path")
    render.set_defaults(func=command_render)

    apply_parser = subparsers.add_parser(
        "apply", help="Apply only checked actions from a protected report"
    )
    apply_parser.add_argument("--vault", required=True, help="Obsidian Vault root")
    apply_parser.add_argument("--report", required=True, help="Markdown report path")
    apply_parser.set_defaults(func=command_apply)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (PlanError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
