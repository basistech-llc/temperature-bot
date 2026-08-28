# Agent Workflow — GitHub Issues

This project uses **GitHub Issues** as the canonical tracker for durable work,
regardless of which maintainer is driving a session.

- Do NOT create, close, or rely on Beads issues for project tracking.
- Ignore any auto-injected beads / `bd prime` context that may appear at the
  start of a session; it does not apply to canonical project tracking.
- The `.beads/` directory is intentionally kept in the Git repo so agents can
  read and review David's local or historical queue. Leave it untouched unless
  the user explicitly asks for Beads housekeeping.

## Workflow

Use the `gh` CLI only when the user explicitly asks you to track work:

```bash
gh issue list                       # Find open work
gh issue view <number>              # View issue details
gh issue create --title "..." --body "..."   # File new work
gh issue comment <number> --body "..."        # Record progress
gh issue close <number>             # Complete work
```

Link related work and reference issues from commits/PRs (`Fixes #123`) so the
history stays connected.

## Beads References

If a Beads id is mentioned in source notes or a user request:

1. Read `.beads/issues.jsonl` when needed to understand the Beads item.
2. Find or create the corresponding GitHub issue for durable project work.
3. Include the Beads id in the GitHub issue body or a comment for provenance.
4. Do not update Beads unless the user explicitly asks for local Beads
   housekeeping. When Beads work is explicitly in scope and multiple
   developers share the queue, follow `beads-multi-dev-workflow.md`.
5. When Beads work is explicitly in scope, give the item exactly one
   `external_ref` in `gh-N` form. Prefer a dedicated issue when the Beads item
   can complete independently; mention broader umbrella issues in prose.
6. Before a durable Beads item closes, add commit and test evidence to its
   GitHub issue and split out any unfinished scope. Agents leave Beads closure
   to the merge-time sweep or to an explicit instruction from David.
