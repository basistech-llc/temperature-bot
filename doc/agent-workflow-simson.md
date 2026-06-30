# Agent Workflow — GitHub Issues

This project uses **GitHub Issues** as the canonical tracker for durable work,
regardless of which maintainer is driving a session.

- Do NOT create, close, or rely on Beads issues for project tracking.
- Ignore any auto-injected beads / `bd prime` context that may appear at the
  start of a session; it does not apply to canonical project tracking.
- The `.beads/` directory may contain David's local or historical queue; leave
  it untouched unless the user explicitly asks for Beads housekeeping.

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

1. Find or create the corresponding GitHub issue.
2. Include the Beads id in the GitHub issue body or a comment for provenance.
3. Do not update Beads unless the user explicitly asks for local Beads
   housekeeping.
