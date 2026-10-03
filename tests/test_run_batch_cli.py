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


def test_future_batch_without_as_of_fails_with_a_clear_error_not_a_keyerror(tmp_path, monkeypatch):
    # README.md documents running --batch 4 once office-exports/batch-04/ exists, but
    # AS_OF_BY_BATCH only has entries for 1-3 -- without an override, this must block cleanly
    # (run-log records a clear reason) rather than crash with a raw KeyError traceback.
    _setup_repo(tmp_path)
    _run(tmp_path, monkeypatch, 1)
    batch_four_dir = _make_office_exports_batch(tmp_path, 4)
    state_path = str(tmp_path / "deliverables" / "state" / "batch-01.state.json")
    exit_code = _run(tmp_path, monkeypatch, 4, state_path=state_path)
    assert exit_code == 1
    run_log_text = (tmp_path / "deliverables" / "run-log.md").read_text()
    assert "no --as-of" in run_log_text or "as-of" in run_log_text


def test_future_batch_with_as_of_override_runs(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    _run(tmp_path, monkeypatch, 1)
    _make_office_exports_batch(tmp_path, 4)
    # batch 4's predecessor is batch 3 by convention (args.batch - 1) -- this test is only about
    # the --as-of override, so give it a placeholder batch-03.json to hash rather than actually
    # running batches 2-3 (that chain is already covered by test_batch_two_resumes_from_batch_one_state).
    (tmp_path / "deliverables" / "snapshots" / "batch-03.json").write_text("{}")
    state_path = str(tmp_path / "deliverables" / "state" / "batch-01.state.json")
    monkeypatch.setattr("scripts.run_batch.REPO_ROOT", str(tmp_path))
    argv = ["--batch", "4", "--state", state_path, "--as-of", "2026-06-15"]
    from scripts.run_batch import main as run_main

    exit_code = run_main(argv)
    assert exit_code == 0
    with open(tmp_path / "deliverables" / "snapshots" / "batch-04.json") as f:
        snapshot = json.load(f)
    assert snapshot["as_of"] == "2026-06-15"


def test_force_resupersede_automatically_preserves_the_existing_sealed_bytes(tmp_path, monkeypatch):
    # --force-resupersede is "the only thing standing between a fix and permanent loss of sealed
    # bytes" if the manual copy-aside step is skipped -- it must preserve the existing file
    # itself, not rely on the operator remembering to do it by hand first.
    _setup_repo(tmp_path)
    _run(tmp_path, monkeypatch, 1)
    snapshot_path = tmp_path / "deliverables" / "snapshots" / "batch-01.json"
    original_bytes = snapshot_path.read_bytes()

    # Change the rules so the next run genuinely differs (simulating a real fix).
    rules_path = tmp_path / "deliverables" / "rules.md"
    rules_text = rules_path.read_text()
    rules_path.write_text(rules_text.replace("value: 30", "value: 29", 1))

    exit_code = _run(tmp_path, monkeypatch, 1, force=True)
    assert exit_code == 0

    snapshots_dir = tmp_path / "deliverables" / "snapshots"
    superseded = [p for p in snapshots_dir.iterdir() if "superseded" in p.name]
    assert len(superseded) == 1
    assert superseded[0].read_bytes() == original_bytes
    assert snapshot_path.read_bytes() != original_bytes
