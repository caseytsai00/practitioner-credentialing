from __future__ import annotations

import json
import os

from scripts.run_batch import main

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_real_batch_03_run_resumes_from_batch_02():
    exit_code = main(
        [
            "--batch",
            "3",
            "--state",
            os.path.join(REPO_ROOT, "deliverables", "state", "batch-02.state.json"),
        ]
    )
    assert exit_code == 0

    snapshot_path = os.path.join(REPO_ROOT, "deliverables", "snapshots", "batch-03.json")
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)

    assert snapshot["batch"] == 3
    assert snapshot["as_of"] == "2026-05-18"
    assert snapshot["predecessor"]["path"] == "deliverables/snapshots/batch-02.json"

    with open(os.path.join(REPO_ROOT, "deliverables", "snapshots", "batch-02.json"), encoding="utf-8") as f:
        batch_two_ids = {app["application_id"] for app in json.load(f)["applications"]}
    batch_three_ids = {app["application_id"] for app in snapshot["applications"]}
    assert batch_two_ids.issubset(batch_three_ids)

    # Withdrawal from batch 2 must still be sticky in batch 3.
    by_id = {app["application_id"]: app for app in snapshot["applications"]}
    assert by_id["APP-2026-028"]["status"] == "withdrawn"

    # At least one application should have reached an admitted Governing Body approval by now,
    # given batch-02 and batch-03's decisions folders carry 26 Governing Body "approved" decisions
    # between them.
    assert any(app["approval_decision_id"] is not None for app in snapshot["applications"])
