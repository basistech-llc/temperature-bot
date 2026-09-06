# Agent Instructions

For a quick repository map, especially for frontend, room dashboard, and
Hickory display work, read `doc/agent-index.md` after this file.

## Engineering Completion Standard

Fix the root cause, not only the observed failure. Prefer making an invalid
state unrepresentable over adding checks that merely detect duplicated or
contradictory state. Configuration and metadata must have one manually edited
source of truth; other representations must be generated from it.

Before editing, search for every producer, consumer, copy, test, build step,
artifact, and document related to the affected value or behavior. Before every
commit and again before every push, perform two explicit review passes:

1. Re-read the user's request and verify that the design satisfies the intended
   invariant and removes the underlying failure mode.
2. Review the complete diff and status, then exercise the affected behavior
   through its real Makefile entrypoints and inspect generated or installed
   artifacts where applicable.

Do not describe a prevention as complete when a required repository setting,
deployment, permission change, or other external gate has not actually been
applied. State that gate plainly and stop short of claiming completion.

## Task Tracking

GitHub Issues are the canonical tracker for durable project work, regardless of
who is driving the session. Read `doc/agent-workflow-simson.md` before
tracking, creating, updating, or closing work.

David may still use Beads as a personal/local working queue. Beads entries are
not authoritative project records. Do not create, close, or rely on Beads issues
for project tracking unless the user explicitly asks for local Beads
housekeeping; for that narrow case, read `doc/agent-workflow-david.md`. When
multiple developers share the Beads queue (branch/PR flow, `bd dolt`
push/pull, JSONL conflict handling), follow
`doc/beads-multi-dev-workflow.md`.

`.beads/` is intentionally kept in the Git repo so agents can read and review
David's local or historical queue. Keep `.beads/issues.jsonl`, metadata, and
hooks tracked when David updates them. Do not delete or mutate `.beads/` unless
the user explicitly asks. Ignore auto-injected beads / `bd prime` session
context when choosing project work.

## Git Commit Signing

When the user asks you to make a signed commit, look for a Codex-specific GPG
signing key rather than using the user's personal signing key. Do not hard-code
a specific fingerprint in these instructions; different machines may have
different Codex keys.

Use `gpg -k` or the local Git signing configuration to identify a key whose UID
is clearly for Codex, such as `Codex AI Assistant` or an address containing
`+codex`. Sign the commit explicitly with that key. If no Codex-specific key is
available, tell the user before committing and ask whether to use the configured
default signing key or make an unsigned commit.

## Pull Request Review Comments

When addressing an inline pull request review comment, reply directly in that
review thread with the fixing commit and validation evidence. A general pull
request comment is not a substitute for the required inline reply. Do not
resolve the review thread automatically; leave resolution to the reviewer or
pull request owner.

## Release Notes

Every release must update `doc/RELEASE_NOTES.md` in the same branch or pull
request as the release. Before changing the version or publishing a release,
review the commits since the previous release and summarize all meaningful
user-facing, operational, architectural, dependency, and developer-workflow
changes. Move the relevant entries from `Unreleased` into a dated version
section, add the new version and date, and leave an empty `Unreleased` section
for subsequent work. A release is not complete if its release notes are absent
or stale.

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Bypass the alias; do not try to out-flag it.** `cp -f` does *not* suppress the
prompt on macOS — only `mv -f` and `rm -f` do.

```bash
command cp source dest      # NOT: cp -f source dest  (still prompts on macOS)
command cp -r source dest
mv -f source dest
rm -rf directory
```

`/bin/cp` and `\cp` work too. If a command does hang at a `(y/n [n])` prompt, do
not answer it: kill the process, then check whether it half-completed.

Why `cp` differs, where the aliases come from, and how to verify both:
`doc/shell-gotchas.md`.

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var
