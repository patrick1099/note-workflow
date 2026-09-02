# Archive ownership rules

Use this order:

0. Ignore `98-Resources/原稿归档`; it is immutable version provenance, not a
   destination candidate for polished notes and not a source of archive work.
1. Keep notes still owned by a concrete task or project under its existing
   `01-任务需求` or `02-项目计划` area.
2. Move knowledge that remains useful outside a project to `00-知识树`.
3. Place external original material, manuals, and protocol sources under
   `98-Resources`.
4. Archive an entire project only when the user explicitly requests that
   project-level operation.

Choose one primary folder. Express secondary domains with `topics` and links;
never duplicate the note into several folders.

Prefer existing folders. Propose a new knowledge folder only when all relevant
conditions hold:

- It is inside an allowed extensible area such as `00-知识树`.
- No existing folder has the same or a near-equivalent meaning.
- At least three complete notes share the stable topic, or the user explicitly
  requests the folder.
- The name is a stable knowledge concept, not a temporary task.
- The resulting hierarchy is at most two levels deep.

Folder creation is its own `mkdir` action. A move that requires it must list the
folder action ID as a dependency.

Do not move a note merely because its `kind` changed. `kind` describes how the
document is used; it is not a folder taxonomy.

## Folder discipline

Folders are taxonomy, not drawers; dropping a note into an existing folder is
not a completed classification. Before proposing any move:

1. **Folder contract.** If the destination folder contains an `AGENTS.md`, read
   it first. It declares the folder's scope, naming rules, and size thresholds,
   and it overrides the generic ownership order above. A move that violates the
   contract goes back to planning, not through.
2. **Flat-size ceiling.** A leaf folder with 15 or more notes directly inside is
   at capacity: prefer proposing thematic subfolders (per the new-folder
   conditions above) over adding another note. Task folders (`01-任务需求/*`)
   group by sub-topic the same way (协议 / 显示 / 清单 / 会议…).
3. **Catch-all folders** (`0_其他`, `misc`, `archive`): only notes that fit
   nowhere else belong there; "related to something already inside" is not a
   reason. Past 20 notes, the next archive round must propose promoting stable
   clusters (3+ notes on one stable topic) into real folders, plus an index/MOC
   for what remains.
4. **Index duty.** If the destination contract names an index/MOC note, the
   move's reason line must note that the links stage owes that index an entry.
5. **New folders get contracts.** When a `mkdir` proposal creates a folder, its
   reason must sketch the scope for a future `AGENTS.md` contract (scope /
   not-scope / thresholds); the contract file itself is authored by the user or
   a separate approved step, not smuggled in during apply.

`scripts/consistency_check.py` flags folders at or above 20 direct notes as
`folder_bloat`; treat that finding as a mandatory planning input for the next
archive round, not as optional advice.
