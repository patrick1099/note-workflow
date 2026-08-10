---
name: archive-notes
description: Plan and execute human-approved Obsidian folder creation and note moves after the user has accepted a note. Use when complete is true and archive_done is false, when the user asks where a finished note belongs, or when the user asks to resume an archive Dry Run. This skill never rewrites note bodies or creates knowledge links.
---

# Archive Notes

Read [note-schema.md](../../shared/note-schema.md),
[dry-run-schema.md](../../shared/dry-run-schema.md), and
[archive-rules.md](references/archive-rules.md) before planning.

## Entry gate

Require `complete: true` for every subject note. An explicitly selected note may
run without `ai_done: true`, but the user must still own the `complete` decision.
Keep `archive_done: false` while any proposal, dependency, question, or failed
action remains open.
Reject subjects under `98-Resources/原稿归档`. Those files are immutable
pre-polish sources and are not final knowledge-location candidates.

## Plan

1. Re-read the current Vault tree and the complete note.
2. Prefer an existing folder. Use the ordered ownership rules in
   `archive-rules.md`; never map the eight `kind` values to eight folders.
3. Propose only folder creation, file moves, or a `decision` to keep the current
   location. Do not add links or edit note bodies.
4. Make every folder and move a separate action with a stable ID, reason,
   dependencies, and blank suggestion field.
5. Write a versioned JSON plan to a temporary location and render a new
   versioned Markdown report through the shared engine:

   ```text
   python <plugin-root>/scripts/action_engine.py render \
     --vault <vault-root> --plan <plan.json> --report <dry-run.md>
   ```

Resolve `<plugin-root>` from this skill's installed location. Never hand-write a
report that will later be applied.

## Approval and apply

Only the user may change report checkboxes or suggestion lines.

Verbal-approval bridge: when the user explicitly approves an action in chat (e.g.
"执行"、"apply、都做"), the agent may record that approval by ticking the
corresponding checkbox before `apply`, and must note the approval source in the
action's `- 建议：` line (e.g. "用户对话批准：<quote>"). This is the only case
where the agent writes a checkbox. Never treat silence, a non-answer, or an
unrelated "yes" as approval.

- Execute checked actions through `action_engine.py apply`.
- Do not execute unchecked actions.
- If an unchecked action has advice, retain that advice and create a new plan
  and a new report version with new action IDs.
- If it has no advice, leave it pending or ask one concrete question.
- If a checked action is stale or blocked, create a new Dry Run; do not broaden
  the old approval.

The engine embeds the exact plan in the report, checks protected report text and
file hashes, backs up affected files, and refuses drift.

## Close

After applying checked actions, verify current paths and read the receipt. Set
`archive_done: true` only when every proposal has been executed, replaced,
explicitly cancelled, or resolved by an approved keep-location decision.

If a completed archive round moved or renamed a note in a way that requires link
revalidation, set `links_done: false`. Never set or clear `complete`.
