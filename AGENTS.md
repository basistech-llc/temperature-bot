# Agent Instructions

For a quick repository map, especially for frontend, room dashboard, and
Hickory display work, read `doc/agent-index.md` after this file.

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
