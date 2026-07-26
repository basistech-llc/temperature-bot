"""Tests for bin/beads_pr_sweep.py classification logic.

The sweep decides whether a bead gets closed, stamped, or flagged for human
attention based on PR state. A misrouting here would silently close beads
whose work never merged (losing open work) or leave merged work open
forever, so the routing table is worth pinning down. GitHub and bd access
is monkeypatched; no network or database is touched.
"""

from bin import beads_pr_sweep


def _bead(metadata):
    return {"metadata": metadata}


def test_classify_routes_by_pr_state(monkeypatch):
    """Merged -> close, closed-unmerged -> attention, open -> waiting.

    Covers the core routing: only a MERGED PR may close a bead. A bead
    whose PR was closed without merge must surface as [!] attention, never
    be closed -- that was the design decision behind the sweep.
    """
    states = {101: "MERGED", 102: "CLOSED", 103: "OPEN"}
    monkeypatch.setattr(beads_pr_sweep, "pr_state", lambda n: {"state": states[n]})

    sweep = beads_pr_sweep.Sweep()
    sweep.classify_bead("hvac-aaa", _bead({"pr": 101}))
    sweep.classify_bead("hvac-bbb", _bead({"pr": 102}))
    sweep.classify_bead("hvac-ccc", _bead({"pr": 103}))

    assert sweep.to_close == {101: ["hvac-aaa"]}
    assert any("hvac-bbb" in line for line in sweep.attention)
    assert any("hvac-ccc" in line for line in sweep.waiting)
    assert not sweep.to_stamp


def test_classify_branch_only_proposes_stamp(monkeypatch):
    """A bead with branch metadata but no pr gets a pr= stamp proposal.

    Prevents regressing the discovery path that upgrades branch linkage to
    PR linkage once the PR exists (and leaves the bead waiting when the
    branch has no PR yet).
    """
    monkeypatch.setattr(
        beads_pr_sweep,
        "pr_for_branch",
        lambda b: {"number": 204} if b == "task/with-pr" else None,
    )

    sweep = beads_pr_sweep.Sweep()
    sweep.classify_bead("hvac-ddd", _bead({"branch": "task/with-pr"}))
    sweep.classify_bead("hvac-eee", _bead({"branch": "task/no-pr"}))
    sweep.classify_bead("hvac-fff", _bead({}))  # no linkage at all

    assert sweep.to_stamp == {"hvac-ddd": 204}
    assert any("no PR yet" in line for line in sweep.waiting)
    assert len(sweep.waiting) == 1  # unlinked bead is silent, not noise


def test_pr_read_failure_flags_attention_not_crash(monkeypatch):
    """A gh failure on one bead must not abort the whole sweep.

    Multiple beads share one sweep; a deleted PR or gh hiccup on one bead
    should degrade to an [!] line, not an unhandled exception.
    """

    def boom(_n):
        raise RuntimeError("gh: not found")

    monkeypatch.setattr(beads_pr_sweep, "pr_state", boom)

    sweep = beads_pr_sweep.Sweep()
    sweep.classify_bead("hvac-ggg", _bead({"pr": 999}))

    assert any("cannot read PR #999" in line for line in sweep.attention)


def test_scan_hits_exclude_already_handled_beads():
    """Commit-scan mentions dedupe against stamp/close actions.

    Without this, a bead being closed via its pr metadata would ALSO show
    as a [?] manual-review line for the same PR, teaching users to ignore
    the [?] section.
    """
    sweep = beads_pr_sweep.Sweep()
    sweep.to_close = {201: ["hvac-aaa"]}
    sweep.to_stamp = {"hvac-bbb": 202}

    beads = {"hvac-aaa": {}, "hvac-bbb": {}, "hvac-ccc": {}}
    mentions = {
        "hvac-aaa": [201],  # already closing
        "hvac-bbb": [202],  # already stamping
        "hvac-ccc": [203],  # genuinely unstamped
        "hvac-zzz": [204],  # not an open bead
    }
    sweep.add_scan_hits(mentions, beads)

    assert sweep.scan_hits == {"hvac-ccc": [203]}
