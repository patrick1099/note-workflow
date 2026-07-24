---
name: organize-notes
description: Organize and classify selected Obsidian Markdown notes while preserving user text and unknown frontmatter. Use when the user asks to 整理笔记、分类、补全属性、提取 topics、按反馈重写，or process notes whose ai_done is false. This skill owns ai_done, kind, topics, and AI-authored organization, but never moves files or creates inter-note links.
---

# Organize Notes

Read [note-schema.md](../../shared/note-schema.md) and
[kinds.md](references/kinds.md) before changing a note.

## Scope

Process only files, folders, or `AI待处理` locations explicitly selected by the
user. Never start with a Vault-wide write scan. Skip credentials, private notes,
excluded directories, and non-Markdown files.

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
5. Honor the requested depth:
   - For classification or tagging, update properties only.
   - For organizing or rewriting, preserve user material and replace only
     clearly AI-authored sections.
6. If a missing decision would materially change the result, ask one concrete
   question. In background work, write it to `ai_question`, keep
   `ai_done: false`, and stop that note.
7. Validate the result, then set `ai_done: true`. Keep `complete` unchanged.

## Rework

Treat non-empty `ai_feedback` as requirements, not disposable scratch text.
Respond to every actionable point and retain the original feedback for review.
When a new organization round can affect location or relationships, set
`archive_done: false` and `links_done: false`.

## Completion

Set `ai_done: true` only when `kind` is legal, `topics` are useful, the requested
editing is complete, user text is preserved, feedback is addressed,
`ai_question` is empty, and no unsupported claim has been promoted to fact.

Never set or clear `complete`. Never move, rename, split, delete, or link notes.
