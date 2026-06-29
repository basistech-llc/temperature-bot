# Agent Instructions

## Task Tracking

This project has two maintainers who use **different** issue trackers. Before
tracking, creating, or closing any work, determine who is driving and follow
their workflow:

1. Check `git config user.email`:
   - `deg@degel.com` → **David** uses Beads — read `doc/agent-workflow-david.md`.
   - `simsong@acm.org` → **Simson** uses GitHub Issues — read `doc/agent-workflow-simson.md`.
2. If the email matches neither (CI, shared/unset identity), ask the user which
   workflow to follow before tracking any work.

`.beads/` is a live workspace for David's workflow; do not delete it. When
Simson is driving, ignore both `.beads/` state and any auto-injected `bd prime`
session context.

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

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var
