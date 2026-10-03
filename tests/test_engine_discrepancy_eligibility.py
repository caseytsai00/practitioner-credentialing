from __future__ import annotations

from scripts.engine import detect_discrepancies, detect_eligibility_mismatch


def test_detect_discrepancies_finds_mismatched_verified_to_date():
    history = [
        {"entry_id": "ENT-1", "from_date": "2019-01-01", "to_date": "2022-08-31"},
    ]
    verification_replies = [
        {"entry_id": "ENT-1", "verified_from": "2019-01-01", "verified_to": "2021-11-30"},
    ]
    discrepancies = detect_discrepancies(history, verification_replies)
    assert len(discrepancies) == 1
    assert discrepancies[0]["field"] == "to_date"
    assert discrepancies[0]["declared"] == "2022-08-31"
    assert discrepancies[0]["verified"] == "2021-11-30"


def test_detect_discrepancies_empty_when_dates_match():
    history = [{"entry_id": "ENT-1", "from_date": "2019-01-01", "to_date": "2022-08-31"}]
    verification_replies = [
        {"entry_id": "ENT-1", "verified_from": "2019-01-01", "verified_to": "2022-08-31"}
    ]
    assert detect_discrepancies(history, verification_replies) == []


def test_eligibility_mismatch_true_when_nothing_supports_requested_privilege():
    priv_requests = [{"privilege_name": "Orthopaedic Surgery"}]
    history = [
        {"entry_type": "residency", "role": "Family Medicine Residency", "organization": "Test Hospital"}
    ]
    credentials = [{"issuer": "American Board of Family Medicine"}]
    assert detect_eligibility_mismatch(priv_requests, history, credentials) is True


def test_eligibility_mismatch_false_when_training_supports_privilege():
    priv_requests = [{"privilege_name": "Family Medicine"}]
    history = [
        {"entry_type": "residency", "role": "Family Medicine Residency", "organization": "Test Hospital"}
    ]
    credentials = []
    assert detect_eligibility_mismatch(priv_requests, history, credentials) is False


def test_eligibility_mismatch_false_with_no_privilege_requests():
    assert detect_eligibility_mismatch([], [], []) is False


def test_detect_ppq_findings_true_when_any_disclosure_answered_yes():
    from scripts.engine import detect_ppq_findings

    disclosures = [
        {"question_code": "PPQ-1", "answer": "No", "applicant_comment": ""},
        {"question_code": "PPQ-2", "answer": "Yes", "applicant_comment": "Explained in attached letter."},
    ]
    assert detect_ppq_findings(disclosures) is True


def test_detect_ppq_findings_false_when_every_disclosure_is_no():
    from scripts.engine import detect_ppq_findings

    disclosures = [{"question_code": "PPQ-1", "answer": "No", "applicant_comment": ""}]
    assert detect_ppq_findings(disclosures) is False
