from __future__ import annotations

import json
import os
import shutil

from scripts.run_batch import main

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
MINI_BATCH_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "mini-batch")


def _make_office_exports_batch(tmp_path, batch_num):
    target = tmp_path / "office-exports" / "batch-{:02d}".format(batch_num)
    shutil.copytree(MINI_BATCH_DIR, target)
    return target


def _run(tmp_path, monkeypatch, batch_num, state_path=None, force=False):
    monkeypatch.setattr("scripts.run_batch.REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "scripts.run_batch.AS_OF_BY_BATCH", {1: "2026-03-16", 2: "2026-04-20", 3: "2026-05-18"}
    )
    argv = ["--batch", str(batch_num)]
    if state_path:
        argv += ["--state", state_path]
    if force:
        argv += ["--force-resupersede"]
    return main(argv)


def _setup_repo(tmp_path):
    _make_office_exports_batch(tmp_path, 1)
    rules_src = os.path.join(REPO_ROOT, "deliverables", "rules.md")
    rules_dst = tmp_path / "deliverables" / "rules.md"
    os.makedirs(rules_dst.parent, exist_ok=True)
    shutil.copyfile(rules_src, rules_dst)
    schema_src = os.path.join(REPO_ROOT, "snapshot.schema.json")
    shutil.copyfile(schema_src, tmp_path / "snapshot.schema.json")


def test_first_run_produces_a_valid_sealed_snapshot(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    exit_code = _run(tmp_path, monkeypatch, 1)
    assert exit_code == 0

    snapshot_path = tmp_path / "deliverables" / "snapshots" / "batch-01.json"
    assert snapshot_path.exists()
    with open(snapshot_path) as f:
        snapshot = json.load(f)
    assert snapshot["batch"] == 1
    assert snapshot["predecessor"] is None
    assert snapshot["as_of"] == "2026-03-16"

    state_path = tmp_path / "deliverables" / "state" / "batch-01.state.json"
    assert state_path.exists()

    run_log_path = tmp_path / "deliverables" / "run-log.md"
    assert run_log_path.exists()
    assert "supported" in run_log_path.read_text()


def test_rerunning_same_batch_unchanged_leaves_snapshot_bytes_identical(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    _run(tmp_path, monkeypatch, 1)
    snapshot_path = tmp_path / "deliverables" / "snapshots" / "batch-01.json"
    first_bytes = snapshot_path.read_bytes()

    exit_code = _run(tmp_path, monkeypatch, 1)
    assert exit_code == 0
    second_bytes = snapshot_path.read_bytes()
    assert first_bytes == second_bytes


def test_batch_two_resumes_from_batch_one_state(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    _run(tmp_path, monkeypatch, 1)
    _make_office_exports_batch(tmp_path, 2)

    state_path = str(tmp_path / "deliverables" / "state" / "batch-01.state.json")
    exit_code = _run(tmp_path, monkeypatch, 2, state_path=state_path)
    assert exit_code == 0

    snapshot_path = tmp_path / "deliverables" / "snapshots" / "batch-02.json"
    with open(snapshot_path) as f:
        snapshot = json.load(f)
    assert snapshot["predecessor"]["path"] == "deliverables/snapshots/batch-01.json"
    assert len(snapshot["predecessor"]["sha256"]) == 64


def test_blocked_batch_does_not_touch_prior_sealed_snapshot(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    _run(tmp_path, monkeypatch, 1)
    snapshot_path = tmp_path / "deliverables" / "snapshots" / "batch-01.json"
    original_bytes = snapshot_path.read_bytes()

    # Batch 2's directory is missing a required CSV entirely -- this must block, not crash past it.
    batch_two_dir = _make_office_exports_batch(tmp_path, 2)
    os.remove(batch_two_dir / "applications.csv")

    state_path = str(tmp_path / "deliverables" / "state" / "batch-01.state.json")
    exit_code = _run(tmp_path, monkeypatch, 2, state_path=state_path)
    assert exit_code == 1

    # batch-01's sealed snapshot must be completely untouched.
    assert snapshot_path.read_bytes() == original_bytes
    # batch-02 must not have produced a snapshot claiming uncomputed state.
    assert not (tmp_path / "deliverables" / "snapshots" / "batch-02.json").exists()

    run_log_text = (tmp_path / "deliverables" / "run-log.md").read_text()
    assert "blocked" in run_log_text
