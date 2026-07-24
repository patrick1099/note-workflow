# Archive ownership rules

Use this order:

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
