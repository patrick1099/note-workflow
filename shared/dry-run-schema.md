# Executable Dry Run contract

Use `scripts/action_engine.py` for every archive or link report. The report
embeds the canonical plan and a hash of protected visible text. Applying a
report therefore executes the same actions shown to the user.

## Plan

Use UTF-8 JSON:

```json
{
  "version": 1,
  "stage": "archive",
  "title": "笔记归档 Dry Run v1",
  "actions": [
    {
      "id": "F-001",
      "type": "mkdir",
      "path": "00-知识树/GPRS通信",
      "summary": "创建 GPRS 通信知识目录",
      "reason": "已有至少三篇完整笔记",
      "dependencies": []
    },
    {
      "id": "M-001",
      "type": "move",
      "source": "AI结果/GPRS模块接收链路.md",
      "target": "00-知识树/GPRS通信/GPRS模块接收链路.md",
      "summary": "迁移完整知识笔记",
      "reason": "内容脱离项目后仍可复用",
      "dependencies": ["F-001"]
    }
  ]
}
```

Allowed actions:

- Archive stage: `mkdir`, `move`, `decision`.
- Links stage: `edit`, `decision`.

An `edit` action is atomic across all listed files:

```json
{
  "id": "L-001",
  "type": "edit",
  "summary": "建立前置知识双向关系",
  "relation": "前置知识",
  "reason": "B 的解释依赖 A 的机制",
  "dependencies": [],
  "changes": [
    {
      "path": "A.md",
      "replacements": [
        {"old": "原文 A", "new": "修改后 A", "count": 1}
      ]
    },
    {
      "path": "B.md",
      "replacements": [
        {"old": "原文 B", "new": "修改后 B", "count": 1}
      ]
    }
  ]
}
```

`old` must match exactly `count` times. Include insertion context inside `old`;
never use an empty anchor or fuzzy matching. Paths are Vault-relative and may
not escape the Vault.

Use a `decision` action for an approved no-write conclusion such as keeping the
current location or intentionally creating no link.

## Report lifecycle

Render:

```text
python <plugin-root>/scripts/action_engine.py render \
  --vault <vault-root> --plan <plan.json> --report <report.md>
```

The report path must be new. Never overwrite an earlier version.

The user may edit only:

- `- [ ]` to `- [x]` for an approved action.
- The single-line `- 建议：` value.

Apply:

```text
python <plugin-root>/scripts/action_engine.py apply \
  --vault <vault-root> --report <report.md>
```

The engine rejects changed protected text, unknown IDs, stale file hashes,
missing dependencies, path escape, overwrite, missing anchors, or inconsistent
bidirectional edits. It creates backups before writes and a sibling receipt
JSON after the run.

Unchecked actions are never executed. Suggestions require AI replanning into a
new report with new IDs. Approval is exact and one-time; drift requires a new
Dry Run.
