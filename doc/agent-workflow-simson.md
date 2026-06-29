# Agent Workflow — Simson (GitHub Issues)

When **Simson** (`simsong@acm.org`) is driving, this project uses **GitHub
Issues** for task tracking, not Beads.

- Do NOT run `bd` commands, create Beads issues, or rely on `.beads/` state.
- Ignore any auto-injected beads / `bd prime` context that may appear at the
  start of a session — it does not apply to this workflow.
- The `.beads/` directory is committed for David's workflow; leave it untouched.

## Workflow

Use the `gh` CLI, and only when the user explicitly asks you to track work:

```bash
gh issue list                       # Find open work
gh issue view <number>              # View issue details
gh issue create --title "..." --body "..."   # File new work
gh issue comment <number> --body "..."        # Record progress
gh issue close <number>             # Complete work
```

Link related work and reference issues from commits/PRs (`Fixes #123`) so the
history stays connected.

> **Note:** This is a minimal starting point restored from the prior, all-Beads
> instructions — there was no recorded GitHub-Issues workflow to copy. Simson
> should refine this file to match his actual preferences (labels, milestones,
> project boards, PR conventions).
