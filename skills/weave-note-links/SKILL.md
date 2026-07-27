---
name: weave-note-links
description: Analyze knowledge relationships and execute human-approved Obsidian Wiki-link insertion or minimal link reflow. Use when a complete note needs related notes, backlinks, prerequisite/source/case links, when links should move from a footer into the body, or when links_done is false. This skill uses exact Dry Runs and never moves files or broadly rewrites accepted prose.
---

# Weave Note Links

Read [note-schema.md](../../shared/note-schema.md),
[dry-run-schema.md](../../shared/dry-run-schema.md), and
[link-placement.md](references/link-placement.md) before planning.

## Entry gate

For automatic batches, require:

```text
complete == true
archive_done == true
links_done != true
```

For an explicitly selected complete note, allow standalone use without a prior
archive round. Never change `complete`.
Never edit or select a note under `98-Resources/原稿归档`.

## Analyze

1. Read the full subject note and search likely related notes by stable title,
   existing links, folders, and topics. A read-only candidate search may inspect
   the Vault, but do not send the whole Vault to an external service.
2. Require an explainable relationship: prerequisite, later application,
   source/evidence, related case, or ordinary relation. Shared topics alone are
   insufficient.
3. Choose the least invasive useful position using `link-placement.md`.
4. Represent one directed bidirectional relationship as one atomic `edit`
   action. Include every affected file and every exact replacement in that
   action.
5. If no link is useful, propose an explicit `decision` action so the user can
   confirm that this round intentionally makes no change.

The polished note's footer link to `98-Resources/原稿归档` is provenance, not a
knowledge relationship. Preserve it as a deliberate one-way link and never
propose or require a backlink in the archived original.

## Dry Run

Create a versioned plan and render it with:

```text
python <plugin-root>/scripts/action_engine.py render \
  --vault <vault-root> --plan <plan.json> --report <dry-run.md>
```

The generated report must show each file, anchor, exact before/after text,
relationship, reason, dependencies, checkbox, and suggestion line. Do not
manually reconstruct the apply operation from prose.

## Apply and revise

Apply only checked actions through `action_engine.py apply`. If the user rejects
an action or changes its location, relationship, or wording, keep the feedback
and create a new report version with a new action ID. Never partially apply an
atomic relationship.

If a file hash, link anchor, or protected report line changed after rendering,
stop and regenerate. Do not fuzzy-match an accepted document.

## Close

Verify that every target note exists, both sides of approved relationships were
written, no protected code/log/quotation text changed, and no unapproved text
changed. Set `links_done: true` only after all proposals are executed,
cancelled, or resolved by an approved no-link decision.
