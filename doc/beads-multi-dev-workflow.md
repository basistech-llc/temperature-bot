# Beads Multi-Developer Workflow

How to use Beads (`bd`) when several developers share the queue and code lands
via branch -> PR -> review -> merge. Written for humans and agents alike.

Scope: this covers *how* to sync and operate Beads. *What* belongs in Beads vs
GitHub Issues is defined in `agent-workflow-simson.md` (GitHub Issues are the
canonical tracker for durable project work) and `agent-workflow-david.md`
(Beads as a working queue). Cross-link bead ids and GitHub issue numbers when
work moves between them.

## Setup in this repo

- Beads runs in Dolt server mode; issue prefix is `hvac`.
- The Dolt remote `origin` is this same GitHub repo
  (`git+ssh://...basistech-llc/temperature-bot.git`). Dolt data lives under
  separate refs, invisible to normal git operations.
- `.beads/issues.jsonl` is a **generated export/backup** (auto-refreshed
  ~every 15 minutes). It is tracked in git for review and recovery, but it is
  not the sync channel and is never authoritative.

## Core principle

**Issue state does not travel through PRs.** Code flows branch -> PR -> merge;
Beads state flows directly between developers via `bd dolt push` /
`bd dolt pull`, out-of-band from git branches. A claim or close you push is
visible to teammates immediately, even while your code branch is still in
review. Do not wait for a merge to sync issue state.

## Workflow

Use this flow when Beads work is in scope (see Scope above). Where a
GitHub issue exists, reference the bead id *alongside* the GitHub issue
number, never instead of it. The imperatives below are written for human
developers; agents follow the same steps but defer `bd dolt push` and
`git push` per "Rules for agents" at the end.

**Session start (and before picking work):**

```bash
git pull                 # or your normal branch update
bd dolt pull             # get teammates' issue state
bin/beads_pr_sweep.py    # dry run: spot beads gone stale vs PR state
bd ready                 # what's unblocked and unclaimed
```

**Starting a task:**

```bash
bd show hvac-NN
bd update hvac-NN --claim   # claim — becomes the mutex once pushed
bd dolt push                # publish the claim now, not at merge time
git checkout -b hvac-NN-short-description
```

Reference the bead id in the branch name, commits, and PR description.
End the first line of each commit message with the bead id in parentheses,
e.g. `Fix damper hysteresis (hvac-NN)` — the PR sweep (below) greps for it.

**During work:** file discovered problems as you go
(`bd create ... --deps discovered-from:hvac-NN`) and `bd dolt push` state
changes that matter to others.

**When you commit bead work to the branch** (first commit is enough),
record the branch on the bead so merge-time reconciliation can find it:

```bash
bd update hvac-NN --set-metadata branch=$(git branch --show-current)
```

**When the PR opens**, stamp every bead riding it (several beads per
branch/PR is normal) and list the bead ids in the PR description:

```bash
bd update hvac-NN --set-metadata pr=204   # repeat for each bead in the PR
```

**At PR merge (not at branch push)** — whoever merges runs:

```bash
bin/beads_pr_sweep.py --close   # closes every bead stamped with the merged PR
bd dolt push
```

Without `gh` available, fall back to closing manually, one
`bd close hvac-NN --reason "Merged in PR #NNN"` per bead.

Close on merge, not on "code done" — a PR can be sent back in review, and an
open in-review bead tells the truth better than a closed one. The
session-start sweep finds beads whose PR has merged, so nothing is lost if
this step is missed.

## Automation: the PR sweep

`bin/beads_pr_sweep.py` reconciles open beads against GitHub PR state using
the `branch`/`pr` metadata stamped above (requires `gh`, authenticated):

```bash
bin/beads_pr_sweep.py           # dry run: report only
bin/beads_pr_sweep.py --close   # stamp discovered PR numbers, close merged
```

It reports beads whose PR is still open, proposes `pr=` stamps for beads
whose branch has grown a PR, closes beads whose PR merged (`--close`), and
flags beads whose PR was closed without merging. As a safety net it also
scans recent merged PRs (title, body, commit messages) for bead ids that
were never stamped; those are reported for manual review, never auto-closed,
because a mention alone does not prove the work is complete.

Run it after `bd dolt pull` at session start, or any time after merging a
PR. It never pushes — follow with `bd dolt push` when appropriate.

## The JSONL file: where PRs and Beads collide

`.beads/issues.jsonl` is the only Beads artifact that rides code branches, so
it is the only place merge conflicts appear.

- Never hand-edit or hand-merge it. On conflict, take either side arbitrarily,
  finish the git merge, then regenerate from Dolt (which is authoritative)
  with `bd export -o .beads/issues.jsonl` and commit the regenerated file.
- Prefer landing JSONL churn on `main` in its own commits; keep large
  generated diffs out of feature PRs where practical.
- `bd import --dry-run` is shallow — do not rely on it to audit differences.
  To preview what a push will change, use `bd-dolt-diff` (David's helper
  script from `degel/beads-utils`, not a bd built-in) or `bd dolt` diff
  commands directly.

Dolt merges at the cell level (per-field): concurrent edits to *different*
issues or different fields never conflict; only concurrent edits to the same
field of the same issue do.

## Rules for agents

- `bd dolt pull` before reading queue state; stale state causes double-claims.
- Claim (`bd update <id> --claim`) before writing code against a bead.
- Do not run `bd dolt push` or `git push` without explicit user authority
  (conservative default); instead report the pending commands at session end.
- Do not mutate or delete `.beads/`; treat `issues.jsonl` as generated output.
