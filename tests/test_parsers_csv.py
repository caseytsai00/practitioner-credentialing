from __future__ import annotations

import os

from scripts.parsers import BatchData, filter_rows, load_csv

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mini-batch")


def test_load_csv_returns_list_of_dicts():
    rows = load_csv(os.path.join(FIXTURE_DIR, "applications.csv"))
    assert len(rows) == 2
    assert rows[0]["application_id"] == "APP-TEST-001"
    assert rows[0]["position_sought"] == "Staff Physician, Family Medicine"


def test_filter_rows_matches_on_kwargs():
    rows = load_csv(os.path.join(FIXTURE_DIR, "declared-history.csv"))
    matched = filter_rows(rows, application_id="APP-TEST-001", entry_type="employment")
    assert len(matched) == 1
    assert matched[0]["entry_id"] == "ENT-T101"


def test_batch_data_loads_every_csv_and_lists_application_ids():
    batch = BatchData(FIXTURE_DIR)
    assert batch.application_ids() == ["APP-TEST-001", "APP-TEST-002"]
    assert len(batch.applications) == 2
    assert len(batch.disclosures) == 2
    assert len(batch.declared_history) == 2
    assert len(batch.declared_credentials) == 1
    assert len(batch.privilege_requests) == 1
    assert len(batch.licence_lookup_wa) == 1
    assert batch.licence_lookup_other == []
    assert batch.certification_replies == []
    assert len(batch.verification_replies) == 1
    assert len(batch.verification_attempts) == 1
    assert len(batch.peer_referees) == 2
    assert len(batch.peer_reference_replies) == 2
    assert len(batch.correspondence) == 1
