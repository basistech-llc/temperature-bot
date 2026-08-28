# Shell Gotchas

Background for the rules in `AGENTS.md`. Nothing here is needed to follow those
rules; it is here so nobody has to re-derive it, and so the rules are not
"fixed" back to something that looks more obvious but does not work.

## `cp -f` does not defeat an `alias cp='cp -i'`

`AGENTS.md` used to recommend `cp -f`. It does not work on macOS, and following
it once left an agent parked for 40 minutes at an unanswered
`overwrite ...? (y/n [n])` prompt.

Verified on macOS 26.3, with no alias involved:

| Command | Result |
| --- | --- |
| `/bin/cp -i -f a b` | prompts, does **not** overwrite |
| `/bin/cp -f -i a b` | prompts, does **not** overwrite |
| `/bin/cp -f a b` | overwrites |
| `COMMAND_MODE=legacy cp -i -f a b` | overwrites |
| `mv -f a b` | overwrites |
| `rm -f b` | removes |

Reproduce the contrast in one line:

```bash
cd "$(mktemp -d)" && printf A > a && printf B > b
COMMAND_MODE=legacy cp -i -f a b   # copies silently
printf B > b
cp -i -f a b                       # prompts
```

### Why

This is standards-conformant behavior, not a bug.

POSIX defines `cp -f` as "if a file descriptor for the destination file cannot
be obtained, attempt to unlink the destination file and proceed" — nothing
about prompting — and specifies no precedence between `-f` and `-i`. The two
are orthogonal. macOS defaults to `COMMAND_MODE=unix2003` (see `compat(5)`), so
`-i` keeps prompting no matter where `-f` appears.

`man cp` is easy to misread here. Its `-f` paragraph says, unqualified:

> (The -f option overrides any previous -i or -n options.)

That describes legacy mode only. The same page's LEGACY DESCRIPTION section
says "In legacy mode, -f will override -i", and `COMMAND_MODE=legacy`
reproduces exactly that. The `-f` paragraph is under-qualified rather than
wrong — but read on its own it looks like a promise that holds by default.

`mv` and `rm` are unaffected because POSIX *does* define their `-f` as "do not
prompt for confirmation". That asymmetry is the whole reason the old advice was
right for two commands out of three.

### Where the aliases come from

Not from this repository. On this developer's machine they come from Oh My Zsh's
`common-aliases` plugin, enabled via `plugins+=(...)` in
`~/core-personal-files/my.oh-my-zsh.zshrc`:

```zsh
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
```

These load in interactive shells only, so scripts and CI never see them — but
agent tooling that sources the user's profile does.

## References

- POSIX `cp`: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/cp.html
- `man 5 compat` for `COMMAND_MODE`
