from __future__ import annotations

import json
import os

from scripts.run_batch import main

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_real_batch_02_run_resumes_from_batch_01():
    exit_code = main(
        [
            "--batch",
            "2",
            "--state",
            os.path.join(REPO_ROOT, "deliverables", "state", "batch-01.state.json"),
        ]
    )
    assert exit_code == 0

    snapshot_path = os.path.join(REPO_ROOT, "deliverables", "snapshots", "batch-02.json")
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)

    assert snapshot["batch"] == 2
    assert snapshot["as_of"] == "2026-04-20"
    assert snapshot["predecessor"]["path"] == "deliverables/snapshots/batch-01.json"
    assert len(snapshot["predecessor"]["sha256"]) == 64

    by_id = {app["application_id"]: app for app in snapshot["applications"]}

    # Every application seen in batch 1 must still be present in batch 2's snapshot -- the
    # caseload carries forward, it never shrinks just because a later batch didn't mention a file.
    with open(os.path.join(REPO_ROOT, "deliverables", "snapshots", "batch-01.json"), encoding="utf-8") as f:
        batch_one_ids = {app["application_id"] for app in json.load(f)["applications"]}
    assert batch_one_ids.issubset(set(by_id.keys()))

    assert by_id["APP-2026-028"]["status"] == "withdrawn"

    app_038 = by_id["APP-2026-038"]
    mec_036 = next(d for d in app_038["decisions"] if d["decision_id"] == "MEC-2026-036")
    assert mec_036["admitted"] is False
    assert mec_036["reason"] is not None
