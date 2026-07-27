---
name: organize-notes
description: Read, classify, and selectively polish selected Obsidian Markdown notes while preserving originals and unknown frontmatter. Use when the user asks to 整理笔记、粗分类、清洗润色、结构化、修正题文不符、补全属性、提取 topics、按反馈重写，or process notes whose ai_done is false. This skill decides after a full read whether a note needs a replacement; when it does, it archives the untouched original and creates a polished note in the original folder with a one-way source link.
---

# Organize Notes

Read [note-schema.md](../../shared/note-schema.md) and
[kinds.md](references/kinds.md) before changing a note.

## Scope

Process only files, folders, or `AI待处理` locations explicitly selected by the
user. Never start with a Vault-wide write scan. Skip credentials, private notes,
excluded directories, and non-Markdown files.
Never process notes under `98-Resources/原稿归档`; they are immutable source
copies, not workflow subjects.

## Workflow

1. Read each whole note, including frontmatter, user text, links, attachments,
   quotations, logs, and the current `ai_feedback`.
2. Apply the state guards from `note-schema.md`.
   - Wait when `ai_done: true` and `complete` is not true.
   - Wait for an answer when `ai_question` is non-empty.
   - Do not revise `complete: true` notes until the user explicitly requests a
     new round and personally clears `complete`.
3. Choose exactly one fixed `kind` using `kinds.md`.
4. Add three to six useful `topics` when the content supports them. Prefer
   normalized topic names already used in the selected Vault.
5. After the full read, choose exactly one handling mode:
   - `metadata_only`: the title matches the content and the body is already
     clear enough to use. Update workflow properties only; do not create a
     duplicate merely to make optional stylistic improvements.
   - `preserve_and_polish`: the title is materially inaccurate or misleading,
     or the body needs meaningful cleanup, correction, deduplication, or
     restructuring to become readable and useful.
6. If a missing decision would materially change the result, ask one concrete
   question. In background work, write it to `ai_question`, keep
   `ai_done: false`, and stop that note.
7. Validate the result, then set `ai_done: true`. Keep `complete` unchanged.

## Metadata-only mode

Keep the current filename, title, and body. Add or update only the durable
workflow frontmatter, preserving unknown keys and their values. Minor style
preferences, short-but-clear notes, and already-structured source/log material
do not justify manufacturing a polished copy.

## Preserve-and-polish mode

Use `scripts/preserve_original.py`; do not reproduce its move/write sequence by
hand.

1. Choose a concise title that matches the main content. Use it for the
   polished note's filename and first H1 when an H1 is present. If the existing
   title already matches, keep it. Reject Windows-reserved names and filename
   characters. If the target filename already exists, stop for a concrete user
   decision; never overwrite or silently add an arbitrary suffix.
2. Keep the polished note in the original note's parent folder.
3. Put the original under:

   ```text
   98-Resources/原稿归档/<original Vault-relative parent>/<original filename>
   ```

   If that path exists, add a timestamp before `.md`; never overwrite an older
   original.
4. Preserve the original file byte-for-byte. Do not add frontmatter, a backlink,
   or any other text to it.
5. Build the polished note from the full source. Preserve facts, user
   conclusions, quotations, logs, code, links, attachments, and unknown
   frontmatter. Improve wording and structure without promoting guesses to
   facts.
6. End the polished note with a one-way provenance link using the full
   Vault-relative path without `.md`:

   ```markdown
   ---
   原稿：[[98-Resources/原稿归档/<original path>|<old title>（原稿）]]
   ```

   This provenance link is intentionally exempt from the bidirectional-link
   rule. Never modify the archived original to add a backlink.
7. Write a UTF-8 JSON plan containing `version`, `source`, `source_sha256`,
   `archive`, `target`, and the complete polished Markdown as `content`. Run the
   same plan through both commands:

   ```text
   python <plugin-root>/scripts/preserve_original.py check \
     --vault <vault-root> --plan <plan.json>
   python <plugin-root>/scripts/preserve_original.py apply \
     --vault <vault-root> --plan <plan.json>
   ```

8. Re-read both paths. Verify the archived bytes match the pre-write SHA256,
   the source path no longer contains the original, the polished note is in the
   original folder, and its source link resolves.

If the current note already contains a provenance link into
`98-Resources/原稿归档`, it is an AI-organized working copy. On user-requested
rework, revise that working copy and retain its existing provenance link; do not
archive it again or create a chain of AI versions.

## Rework

Treat non-empty `ai_feedback` as requirements, not disposable scratch text.
Respond to every actionable point and retain the original feedback for review.
When a new organization round can affect location or relationships, set
`archive_done: false` and `links_done: false`.

## Completion

Set `ai_done: true` only when `kind` is legal, `topics` are useful, the requested
editing is complete, user text is preserved, feedback is addressed,
`ai_question` is empty, and no unsupported claim has been promoted to fact.

Never set or clear `complete`. Never delete an original, add a backlink to an
archived original, or create knowledge-relation links during this stage.
