# Fixed note kinds

Choose one primary use, not every subject mentioned in the note.

| kind | Primary use | Organizing emphasis |
|---|---|---|
| `index` | Navigation, MOC, topic map | Scope and useful links; do not copy source notes |
| `case` | One real incident, diagnosis, fix, verification | Evidence chain; do not claim unverified resolution |
| `design` | Structure, constraints, options, tradeoffs | Separate needs, constraints, choices, and open decisions |
| `plan` | Future work or learning | Goal, dependencies, progress, and next step |
| `log` | Time-ordered chat, work, or runtime trace | Preserve order; extract decisions and unresolved items |
| `source` | External original material | Preserve provenance; summarize without treating it as fact |
| `question` | One unresolved question | Separate known, unknown, hypothesis, and supported answer |
| `knowledge` | Reusable mechanism, method, or conclusion | Clear concepts, relationships, and missing evidence |

Use this tie-break order:

1. `index`
2. `case`
3. `design`
4. `plan`
5. `log`
6. `source`
7. `question`
8. `knowledge`

Keep one `kind` even when several topics are present. Ask the user only when two
kinds would cause materially different organization. Do not split a note merely
to make classification easier.

Legacy mapping:

```text
Notes      -> knowledge
Question   -> question
References -> source
Log        -> log
Plan       -> plan
Design     -> design
ABCD       -> case
MOC        -> index
```

Do not delete the legacy `type` property during an unapproved bulk migration.
