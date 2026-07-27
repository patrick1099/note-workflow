---
name: run-note-workflow
description: Orchestrate the complete Obsidian note workflow by reading durable note states and dispatching organize-notes, archive-notes, and weave-note-links. Use when the user asks to 自动走完整流程、批量处理待整理笔记、继续上次笔记流程，or resume from AI questions, acceptance, archive approval, or link approval. Always pause at human gates.
---

# Run Note Workflow

Read [note-schema.md](../../shared/note-schema.md). This skill is a thin
orchestrator; do not reproduce downstream judgment logic.

## Select and inspect

Accept only explicit note or folder scope. For a batch, inspect durable state
with:

```text
python <plugin-root>/scripts/note_status.py \
  --vault <vault-root> --target <relative-note-or-folder> [...]
```

Never infer continuation from hidden conversation memory when files are
available.
Exclude `98-Resources/原稿归档` from folder and batch subjects.

## Dispatch

For each note:

```text
ai_question is non-empty
    -> wait for the user's answer

ai_done != true
    -> invoke $organize-notes

ai_done == true and complete != true
    -> wait for the user's acceptance

complete == true and archive_done != true
    -> invoke $archive-notes

an archive report still awaits decisions
    -> wait for checkbox or suggestion edits

archive_done == true and links_done != true
    -> invoke $weave-note-links

a link report still awaits decisions
    -> wait for checkbox or suggestion edits

all four booleans are true
    -> complete
```

`organize-notes` may replace a source note with a polished note whose title and
filename changed. After that call, follow its returned target path and re-read
the polished note; do not route the archived original as another subject.
Re-read files after every downstream call and after every user response.

## Human gates

Never set or clear `complete`, tick report checkboxes, treat silence as approval,
discard suggestions, or auto-approve a later stage because an earlier stage
succeeded. “Run everything” means automatically choose and resume safe stages;
it does not remove acceptance or action approval.

When pausing, report the stage, note, exact report or property the user should
edit, and how to resume.

## Batch behavior

Do not let one waiting note block other notes with safe work available. Keep
each note's state independent and end with these groups:

- 已完成全流程
- 等待正文验收
- 等待归档审批
- 等待链接审批
- 等待回答问题
- 执行失败

Do not add `workflow_done`; all four existing booleans already define completion.
If a downstream skill is unavailable or fails, stop that note and report the
failure instead of implementing a substitute inside this skill.
