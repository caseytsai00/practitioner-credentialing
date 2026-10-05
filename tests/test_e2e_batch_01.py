from __future__ import annotations

import json
import os

from scripts.run_batch import main

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_real_batch_01_run_produces_valid_sealed_snapshot():
    exit_code = main(["--batch", "1"])
    assert exit_code == 0

    snapshot_path = os.path.join(REPO_ROOT, "deliverables", "snapshots", "batch-01.json")
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)

    assert snapshot["batch"] == 1
    assert snapshot["as_of"] == "2026-03-16"
    assert snapshot["predecessor"] is None
    # batch-01's applications.csv has 41 rows, but APP-2026-025 already has two revisions within
    # this same batch (its correction landed 2026-02-03, before the 2026-03-15 cutoff) -- the
    # schema wants one entry per application, not per row, so 40 distinct applications is correct.
    assert len(snapshot["applications"]) == 40

    by_id = {app["application_id"]: app for app in snapshot["applications"]}

    assert by_id["APP-2026-019"]["status"] == "intake-incomplete"
    assert by_id["APP-2026-018"]["status"] == "returned-incomplete"
    assert by_id["APP-2026-018"]["elements"]["gaps"] == "return-incomplete"

    # Batch-01 carries only Executive Committee recommendations, never a Governing Body decision --
    # no application can be active, denied, deferred, or decision-inadmissible yet.
    forbidden_statuses = {"active", "active-with-conditions", "denied", "deferred", "decision-inadmissible"}
    for app in snapshot["applications"]:
        assert app["status"] not in forbidden_statuses, "{} unexpectedly {}".format(
            app["application_id"], app["status"]
        )
        if app["decisions"]:
            assert all(d["decision_id"] for d in app["decisions"])

    # Real case: ENT-2201/APP-2026-022 (declared-history.csv, residency at Westmarch University
    # Medical Center). Its only reply, VR-2201 (verification-replies.csv), comes from "Cascade
    # Valley Physicians Society" -- a state medical society confirming "from its own membership
    # file" -- not from Westmarch's own Graduate Medical Education office, which 3 separate
    # attempts (verification-attempts.csv: ATT-2203, ATT-2204, ATT-2205) never got a reply from.
    # Per the interview (05:19-05:20 PM) and the brief ("do not... invent" an accepted source), a
    # reply from an organization other than the one declared must not resolve the element.
    assert by_id["APP-2026-022"]["elements"]["education"] == "outstanding"

    state_path = os.path.join(REPO_ROOT, "deliverables", "state", "batch-01.state.json")
    assert os.path.exists(state_path)
    run_log_path = os.path.join(REPO_ROOT, "deliverables", "run-log.md")
    assert os.path.exists(run_log_path)
