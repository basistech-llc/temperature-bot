# Agent Workflow — David's Local Beads Queue

GitHub Issues are the canonical tracker for durable project work in this repo.
Use `doc/agent-workflow-simson.md` for project issue tracking, including work
driven by David.

David may still use **bd (Beads)** as a personal/local working queue. Beads
entries are not authoritative project records. Only use `bd` when the user
explicitly asks for local Beads housekeeping or asks to inspect/migrate a Beads
entry.

> If a beads SessionStart hook is configured locally, it injects the live,
> local Beads protocol each session. That protocol does not supersede GitHub
> Issues as the canonical project tracker.

## Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>           # Complete work
bd dolt push            # Push beads data to remote
```

## Why bd?

- Dependency-aware: track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready-work detection, discovered-from links
- Useful as David's private queue before durable work is promoted to GitHub

## Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

## Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

## Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

## Workflow for AI Agents

Use this workflow only when the user explicitly asks for local Beads work:

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim the local item atomically**: `bd update <id> --claim`
3. **Work on it**: implement, test, document
4. **Durable follow-up?** Create or update a GitHub issue, then record the
   GitHub issue number in Beads if the user wants the local queue updated.
5. **Local-only follow-up?** Create a linked Beads issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
6. **Complete local item**: `bd close <id> --reason "Done"`

## Quality

- Use `--acceptance` and `--design` fields when creating issues
- Use `--validate` to check description completeness

## Lifecycle

- `bd defer <id>` / `bd supersede <id>` for issue management
- `bd stale` / `bd orphans` / `bd lint` for hygiene
- `bd human <id>` to flag for human decisions
- `bd formula list` / `bd mol pour <name>` for structured workflows

## Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push` / `bd dolt pull` for remote sync
- No manual export/import needed

## Important Rules

- Use GitHub Issues for durable project tracking.
- Use bd only for explicit local Beads housekeeping.
- Always use `--json` flag for programmatic use
- Link local-only discovered work with `discovered-from` dependencies.
- Check `bd ready` only for user-requested local Beads work.
- Do NOT create markdown TODO lists
- Do NOT let Beads become a second authoritative tracker.
- Cross-link Beads ids to GitHub issues when migrating durable work.

## Session Completion

When ending a work session, complete ALL steps below:

1. **File issues for remaining work** - create issues for anything needing follow-up
2. **Run quality gates** (if code changed) - tests, linters, builds
3. **Update issue status** - close finished work, update in-progress items
4. **Sync** - only when the active instructions grant that authority:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status   # confirm state
   ```
5. **Hand off** - provide context for the next session

This is often an ephemeral branch with no upstream. Do not push it unless the
user or orchestrator explicitly says to.
