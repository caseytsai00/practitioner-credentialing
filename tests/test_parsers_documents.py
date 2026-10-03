from __future__ import annotations

import os

from scripts.parsers import BatchData

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mini-batch")


def test_letters_are_parsed_from_filename_and_content():
    batch = BatchData(FIXTURE_DIR)
    letter = batch.letters["2026-01-15_missing-items_APP-TEST-002.md"]
    assert letter["date"] == "2026-01-15"
    assert letter["letter_type"] == "missing-items"
    assert letter["application_id"] == "APP-TEST-002"
    assert "Authorization and Release" in letter["raw_text"]


def test_decisions_are_parsed_by_decision_id():
    batch = BatchData(FIXTURE_DIR)
    decision = batch.decisions["MEC-TEST-001"]
    assert decision["body"] == "Executive Committee of the Medical Staff"
    assert decision["application_id"] == "APP-TEST-001"
    assert decision["revision"] == 1
    assert decision["outcome"] == "recommended"
    assert decision["privileges"] == ["PRIV-FM"]
    assert decision["reason"] is None
    assert decision["effective_date"] is None
    assert decision["filename"] == "2026-02-01_MEC-TEST-001.md"


def test_dispositions_are_parsed_from_filename_and_content():
    batch = BatchData(FIXTURE_DIR)
    disposition = batch.dispositions["2026-01-25_disposition_APP-TEST-001.md"]
    assert disposition["date"] == "2026-01-25"
    assert disposition["application_id"] == "APP-TEST-001"
    assert disposition["recorded_by"] == "Dr. Test Director, MD, Clinical Director"
    assert "no bar to appointment" in disposition["raw_text"]


def test_decision_filenames_helper():
    batch = BatchData(FIXTURE_DIR)
    assert batch.decision_filenames() == ["2026-02-01_MEC-TEST-001.md"]


def test_missing_document_directory_yields_empty_dict(tmp_path):
    # dispositions/ doesn't exist at all in a brand-new empty batch dir -- must not error.
    import shutil

    empty_batch = tmp_path / "empty-batch"
    shutil.copytree(FIXTURE_DIR, empty_batch)
    shutil.rmtree(empty_batch / "dispositions")

    batch = BatchData(str(empty_batch))
    assert batch.dispositions == {}
