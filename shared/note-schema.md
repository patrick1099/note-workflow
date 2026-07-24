# Durable note state

Preserve all unknown frontmatter keys. Add missing workflow keys without
reordering or deleting unrelated properties.

```yaml
---
ai_done: false
complete: false
archive_done: false
links_done: false
ai_question:
ai_feedback:
kind:
topics: []
---
```

| Property | Owner | Meaning |
|---|---|---|
| `ai_done` | `organize-notes` | The requested organization round is complete |
| `complete` | User only | The user has read and accepted the current body |
| `archive_done` | `archive-notes` | Location decisions and approved moves are closed |
| `links_done` | `weave-note-links` | Relationship decisions and approved edits are closed |

No skill may set, clear, or infer `complete`. A generated report is not a
completed stage.

`ai_question` contains at most one short decision-changing question. Keep
`ai_done: false` until it is answered and cleared.

`ai_feedback` is user-owned. Read and honor it; never delete or silently rewrite
it.

State routing:

```text
ai_question non-empty          -> waiting_question
ai_done != true                -> organize
complete != true               -> waiting_acceptance
archive_done != true           -> archive
links_done != true             -> links
otherwise                      -> complete
```

Reset downstream state when upstream facts become invalid:

- A new body/kind/topics organization round sets `archive_done: false` and
  `links_done: false`.
- A rearchive that moves, renames, or invalidates links sets
  `links_done: false`.
- Clearing only `links_done` reruns link analysis without reorganizing or
  rearchiving.

Do not add `workflow_done`.
