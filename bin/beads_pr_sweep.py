#!/usr/bin/env python3
"""Reconcile open beads against GitHub PR state.

Beads carry their branch/PR linkage in metadata (see
doc/beads-multi-dev-workflow.md):

    bd update hvac-NN --set-metadata branch=<branch>   # at first commit
    bd update hvac-NN --set-metadata pr=<number>       # when the PR opens

This script sweeps all open/in_progress beads and reports, per bead:
  - pr metadata + PR merged   -> bead should be closed
  - pr metadata + PR closed unmerged -> needs human attention
  - branch metadata only      -> looks up the PR for that branch, proposes
                                 stamping pr=<number>
It also scans recent merged PRs (title, body, commit messages) for bead ids
that were never stamped, and lists any that are still open.

Dry-run by default. With --close it stamps the proposed pr metadata and
closes beads whose PR merged; commit-scan hits are never auto-closed because
a mention alone does not prove the bead's work is complete. It never runs
`bd dolt push` -- sync remains a human decision.

Requires: bd, gh (authenticated), run from anywhere inside the repo.
"""

import argparse
import json
import re
import subprocess
import sys

MERGED_PR_SCAN_LIMIT = 20


def run(cmd: list[str]) -> str:
    """Run a command, returning stdout; raise with stderr context on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {result.stderr.strip()}")
    return result.stdout


def run_json(cmd: list[str]):
    return json.loads(run(cmd))


def open_beads() -> dict[str, dict]:
    """All open/in_progress beads with metadata (bd list omits metadata)."""
    beads: dict[str, dict] = {}
    for status in ("open", "in_progress"):
        for issue in run_json(["bd", "list", f"--status={status}", "--json"]):
            detail = run_json(["bd", "show", issue["id"], "--json"])
            # bd show --json returns a single-element list in some versions
            if isinstance(detail, list):
                detail = detail[0]
            beads[issue["id"]] = detail
    return beads


def pr_state(number: int) -> dict:
    return run_json(["gh", "pr", "view", str(number), "--json", "state,url,title"])


def pr_for_branch(branch: str) -> dict | None:
    prs = run_json(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,state",
            "--limit",
            "5",
        ]
    )
    return prs[0] if prs else None


def scan_merged_prs(prefix: str, limit: int) -> dict[str, list[int]]:
    """Map bead-id -> merged PR numbers that mention it (title/body/commits)."""
    id_re = re.compile(rf"\b{re.escape(prefix)}-[a-z0-9.]+\b")
    mentions: dict[str, list[int]] = {}
    merged = run_json(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--json",
            "number,title,body",
            "--limit",
            str(limit),
        ]
    )
    for pr in merged:
        text = [pr.get("title", ""), pr.get("body", "")]
        commits = run_json(
            ["gh", "pr", "view", str(pr["number"]), "--json", "commits"]
        ).get("commits", [])
        for commit in commits:
            text.append(commit.get("messageHeadline", ""))
            text.append(commit.get("messageBody", ""))
        for bead_id in id_re.findall("\n".join(text)):
            mentions.setdefault(bead_id, []).append(pr["number"])
    return mentions


class Sweep:
    """Classified reconciliation results for one sweep pass."""

    def __init__(self) -> None:
        self.to_close: dict[int, list[str]] = {}  # pr number -> bead ids
        self.to_stamp: dict[str, int] = {}  # bead id -> pr number
        self.attention: list[str] = []
        self.waiting: list[str] = []
        self.scan_hits: dict[str, list[int]] = {}  # bead id -> merged PRs

    def classify_bead(self, bead_id: str, bead: dict) -> None:
        meta = bead.get("metadata") or {}
        pr_num = meta.get("pr")
        branch = meta.get("branch")
        if pr_num is not None:
            self._classify_by_pr(bead_id, int(pr_num))
        elif branch:
            pr = pr_for_branch(branch)
            if pr:
                self.to_stamp[bead_id] = pr["number"]
            else:
                self.waiting.append(f"{bead_id}: branch {branch}, no PR yet")

    def _classify_by_pr(self, bead_id: str, pr_num: int) -> None:
        try:
            state = pr_state(pr_num)["state"]
        except RuntimeError as exc:
            self.attention.append(f"{bead_id}: cannot read PR #{pr_num} ({exc})")
            return
        if state == "MERGED":
            self.to_close.setdefault(pr_num, []).append(bead_id)
        elif state == "CLOSED":
            self.attention.append(
                f"{bead_id}: PR #{pr_num} closed WITHOUT merge -- rework or abandon?"
            )
        else:
            self.waiting.append(f"{bead_id}: PR #{pr_num} still open")

    def add_scan_hits(self, mentions: dict[str, list[int]], beads: dict) -> None:
        handled = set(self.to_stamp) | {
            b for ids in self.to_close.values() for b in ids
        }
        self.scan_hits = {
            bead_id: prs
            for bead_id, prs in mentions.items()
            if bead_id in beads and bead_id not in handled
        }

    def report(self) -> None:
        for line in self.waiting:
            print(f"[ ] {line}")
        for bead_id, pr_num in sorted(self.to_stamp.items()):
            print(f"[+] {bead_id}: branch has PR #{pr_num} -- stamp pr={pr_num}")
        for pr_num, ids in sorted(self.to_close.items()):
            print(f"[x] PR #{pr_num} merged -- close: {', '.join(sorted(ids))}")
        for bead_id, prs in sorted(self.scan_hits.items()):
            pr_list = ", ".join(f"#{n}" for n in sorted(set(prs)))
            print(
                f"[?] {bead_id}: open, but mentioned in merged PR {pr_list}"
                " -- review manually"
            )
        for line in self.attention:
            print(f"[!] {line}")
        if not any(
            (
                self.waiting,
                self.to_stamp,
                self.to_close,
                self.scan_hits,
                self.attention,
            )
        ):
            print("Nothing to reconcile: no open beads reference a branch or PR.")

    def apply(self) -> None:
        for bead_id, pr_num in sorted(self.to_stamp.items()):
            run(["bd", "update", bead_id, "--set-metadata", f"pr={pr_num}"])
            print(f"stamped {bead_id} pr={pr_num}")
        for pr_num, ids in sorted(self.to_close.items()):
            run(["bd", "close", *sorted(ids), "--reason", f"Merged in PR #{pr_num}"])
            print(f"closed {', '.join(sorted(ids))} (PR #{pr_num})")
        if self.to_stamp or self.to_close:
            print("Remember: bd dolt push when you are ready to publish these updates.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile open beads against GitHub PR state."
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="apply changes: stamp discovered pr metadata, close merged beads",
    )
    parser.add_argument(
        "--merged-limit",
        type=int,
        default=MERGED_PR_SCAN_LIMIT,
        help="how many recent merged PRs to scan for unstamped bead ids",
    )
    args = parser.parse_args()

    prefix = run(["bd", "config", "get", "issue_prefix"]).strip() or "hvac"
    beads = open_beads()

    sweep = Sweep()
    for bead_id, bead in sorted(beads.items()):
        sweep.classify_bead(bead_id, bead)
    sweep.add_scan_hits(scan_merged_prs(prefix, args.merged_limit), beads)

    sweep.report()
    if args.close:
        sweep.apply()
    elif sweep.to_stamp or sweep.to_close:
        print("\nDry run. Re-run with --close to apply the [+] and [x] actions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
