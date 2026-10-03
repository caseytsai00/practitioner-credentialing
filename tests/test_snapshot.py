from __future__ import annotations

import os

import pytest
from jsonschema.exceptions import ValidationError

from scripts.model import ApplicationRecord
from scripts.snapshot import build_snapshot, file_sha256, validate_snapshot

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
SCHEMA_PATH = os.path.join(REPO_ROOT, "snapshot.schema.json")


def _minimal_application():
    return ApplicationRecord(
        application_id="APP-TEST-001",
        revision=1,
        status="in-verification",
        elements={
            "licensure": "resolved",
            "experience": "outstanding",
            "gaps": "resolved",
            "education": "outstanding",
            "certification": "outstanding",
            "references": "outstanding",
        },
        packet_presentable=False,
    )


def test_build_snapshot_produces_expected_shape():
    snapshot = build_snapshot(
        batch=1,
        as_of="2026-03-16",
        predecessor=None,
        consumed={"record_files": ["applications.csv"], "documents": []},
        produced=["deliverables/snapshots/batch-01.json"],
        rules_file="deliverables/rules.md",
        applications=[_minimal_application()],
        snapshot_id="batch-01-test",
    )
    assert snapshot["schema_version"] == "credentialing-snapshot/1"
    assert snapshot["batch"] == 1
    assert snapshot["predecessor"] is None
    assert len(snapshot["applications"]) == 1
    assert snapshot["applications"][0]["application_id"] == "APP-TEST-001"


def test_valid_snapshot_passes_schema_validation():
    snapshot = build_snapshot(
        batch=1,
        as_of="2026-03-16",
        predecessor=None,
        consumed={"record_files": ["applications.csv"], "documents": []},
        produced=["deliverables/snapshots/batch-01.json"],
        rules_file="deliverables/rules.md",
        applications=[_minimal_application()],
        snapshot_id="batch-01-test",
    )
    validate_snapshot(snapshot, SCHEMA_PATH)  # must not raise


def test_invalid_snapshot_fails_schema_validation():
    snapshot = build_snapshot(
        batch=1,
        as_of="not-a-date",  # violates the date pattern
        predecessor=None,
        consumed={"record_files": ["applications.csv"], "documents": []},
        produced=["deliverables/snapshots/batch-01.json"],
        rules_file="deliverables/rules.md",
        applications=[_minimal_application()],
        snapshot_id="batch-01-test",
    )
    with pytest.raises(ValidationError):
        validate_snapshot(snapshot, SCHEMA_PATH)


def test_file_sha256_is_deterministic(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("hello world")
    first = file_sha256(str(path))
    second = file_sha256(str(path))
    assert first == second
    assert len(first) == 64
