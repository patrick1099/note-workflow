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

Never set or clear `complete`, treat silence as approval, discard suggestions, or
auto-approve a later stage because an earlier stage succeeded. In manual approval
mode, never tick report checkboxes yourself. Under explicit delegation (below),
ticking the in-scope actions is allowed and required. “Run everything” means
automatically choose and resume safe stages; it does not remove acceptance or
action approval unless the user delegates it.

Never set `archive_done` or `links_done` yourself to skip real work. Those flags
are closed only by the downstream skill's own apply recipe closing real actions.
Flipping them without executing `archive-notes` / `weave-note-links` produces a
false "complete" that hides still-scattered or still-placeholder notes.

When pausing, report the stage, note, exact report or property the user should
edit, and how to resume.

## Delegated execution

A user may grant full automation ("自动完成"、"交给 subagent 全跑"). That grants
delegation of *decision*, never a license to fake work. When explicitly authorized,
the orchestrator may, for each stage, tick the in-scope actions in the Dry Run
report, then apply via `action_engine.py apply`, without a separate manual
approval step — but it must still do the REAL work:

- organize: real read + kind/topics; placeholder filenames (`未命名`/`Untitled`/`N`)
  must go through preserve-and-polish (new file + provenance link + archived
  original), never a silent in-place rename.
- archive: real location decisions (move/rename/mkdir) via `action_engine.py`.
- links: real weave via `action_engine.py`.

Non-empty selection gate: tick every applicable action before `apply`. If
applicable work exists but the selected set is empty, treat the apply as a
failure and report it — an empty `apply` is a no-op, not a success. Genuinely
"nothing to do" is only true when the stage verifiably has no applicable actions.

Set `archive_done` / `links_done` only after a successful `apply` whose receipt
shows the actions executed and whose postconditions hold. Never treat them as a
selectable "done" action, and never flip them to skip doing the work.

Do not trust the booleans alone: after `apply`, re-check the receipt and the
actual result (moved target exists, old path gone, planned rename/move/link edits
present, `failed == 0` and `applied == selected`). On any mismatch, route the
note to "状态不一致 / 执行失败" instead of continuing to the next stage.

If you cannot reach a real end state (e.g. a decision still outside your
authorization), leave the note at its current stage and report it instead of
marking it done.

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

Before closing a batch, run the read-only consistency check to catch "marked
done but work not done" drift:

```text
python <plugin-root>/scripts/consistency_check.py \
  --vault <vault-root> --target <...each subject folder...>
```

Report any findings (root-not-archived, placeholder names, complete-without-kind)
instead of silently closing the batch.
