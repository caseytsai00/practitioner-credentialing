from __future__ import annotations

import json
import os

from scripts.state import get_application_entry, load_ledger, new_ledger, save_ledger


def test_new_ledger_has_schema_version_and_empty_applications():
    ledger = new_ledger()
    assert ledger["schema_version"] == "credentialing-ledger/1"
    assert ledger["applications"] == {}


def test_get_application_entry_creates_default_shape():
    ledger = new_ledger()
    entry = get_application_entry(ledger, "APP-TEST-001")
    assert entry["revision"] == 0
    assert entry["elements"] == {}
    assert entry["element_evidence"] == {}
    assert entry["decisions_seen"] == []
    assert entry["documents_seen"] == []
    assert entry["status"] is None
    assert entry["approval_decision_id"] is None
    assert entry["activation"] is None
    assert entry["monitored_conditions"] == []
    assert entry["revision_data"] == {}
    assert entry["last_application_row"] is None
    # getting it again returns the same object, not a fresh default
    entry["revision"] = 2
    entry_again = get_application_entry(ledger, "APP-TEST-001")
    assert entry_again["revision"] == 2


def test_load_ledger_with_no_path_returns_new_ledger():
    ledger = load_ledger(None)
    assert ledger["applications"] == {}


def test_save_and_load_ledger_round_trips(tmp_path):
    ledger = new_ledger()
    entry = get_application_entry(ledger, "APP-TEST-001")
    entry["revision"] = 2
    entry["elements"]["licensure"] = "resolved"

    path = str(tmp_path / "batch-01.state.json")
    save_ledger(ledger, path)

    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["applications"]["APP-TEST-001"]["revision"] == 2

    reloaded = load_ledger(path)
    assert reloaded["applications"]["APP-TEST-001"]["elements"]["licensure"] == "resolved"
