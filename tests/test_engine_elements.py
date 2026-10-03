from __future__ import annotations

from scripts.engine import (
    resolve_certification,
    resolve_elements,
    resolve_gaps,
    resolve_licensure,
    resolve_references,
)
from scripts.rules import load_rules
import os

RULES = load_rules(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "deliverables", "rules.md")
)


def test_resolve_licensure_resolved_when_active_and_current():
    credentials = [{"credential_class": "licence", "number_declared": "MD1"}]
    lookup_wa = [
        {"credentialnumber": "MD1", "status": "ACTIVE", "expirationdate": "2030-01-01", "actiontaken": "No"}
    ]
    result = resolve_licensure(credentials, lookup_wa, [], "2026-03-16")
    assert result.state == "resolved"


def test_resolve_licensure_finding_when_board_action_taken():
    credentials = [{"credential_class": "licence", "number_declared": "MD1"}]
    lookup_wa = [
        {"credentialnumber": "MD1", "status": "ACTIVE", "expirationdate": "2030-01-01", "actiontaken": "Yes"}
    ]
    result = resolve_licensure(credentials, lookup_wa, [], "2026-03-16")
    assert result.state == "finding"
    assert result.action_items[0].owner == "Clinical Director"


def test_resolve_licensure_outstanding_when_no_board_match():
    credentials = [{"credential_class": "licence", "number_declared": "MD-UNKNOWN"}]
    result = resolve_licensure(credentials, [], [], "2026-03-16")
    assert result.state == "outstanding"


def test_resolve_certification_resolved_when_active_reply_on_file():
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "ABFM"}]
    replies = [{"declaration_id": "DEC-1", "received_date": "2026-02-01", "certification_status": "Active"}]
    result = resolve_certification(credentials, replies, "2026-03-16")
    assert result.state == "resolved"


def test_resolve_certification_finding_when_lapsed():
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "ABS"}]
    replies = [{"declaration_id": "DEC-1", "received_date": "2026-02-01", "certification_status": "Lapsed"}]
    result = resolve_certification(credentials, replies, "2026-03-16")
    assert result.state == "finding"


def test_resolve_references_resolved_with_two_qualifying_replies():
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [
        {"referee_id": "REF-1", "related_or_partner": "No", "signature_date": "2026-01-01"},
        {"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"},
    ]
    result = resolve_references(referees, replies, [], "2026-03-16", RULES)
    assert result.state == "resolved"


def test_resolve_references_excludes_related_or_partner_reply():
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [
        {"referee_id": "REF-1", "related_or_partner": "Yes", "signature_date": "2026-01-01"},
        {"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"},
    ]
    result = resolve_references(referees, replies, [], "2026-03-16", RULES)
    assert result.state == "outstanding"
    assert any("does not count" in item.item for item in result.action_items)


def test_resolve_references_stale_after_two_years_reverts_to_outstanding():
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [
        {"referee_id": "REF-1", "related_or_partner": "No", "signature_date": "2024-05-05"},
        {"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"},
    ]
    result = resolve_references(referees, replies, [], "2026-05-06", RULES)
    assert result.state == "outstanding"
    assert any("no longer current" in item.item for item in result.action_items)


def test_resolve_gaps_resolved_when_no_qualifying_gap():
    result = resolve_gaps("APP-X", [], [], RULES)
    assert result.state == "resolved"


def test_resolve_gaps_finding_when_explained_gap_awaits_cd_judgment():
    history = [
        {"from_date": "2020-01-01", "to_date": "2020-06-01"},
        {"from_date": "2020-07-15", "to_date": "2026-01-01"},
    ]
    correspondence = [
        {
            "application_id": "APP-X",
            "direction": "inbound",
            "subject": "Explanation of period 2020-06-02 to 2020-07-14",
        }
    ]
    result = resolve_gaps("APP-X", history, correspondence, RULES)
    assert result.state == "finding"
    assert result.evidence["gap_from"] == "2020-06-02"
    assert result.evidence["gap_to"] == "2020-07-14"


def test_resolve_elements_covers_all_six_names():
    results = resolve_elements(
        application_id="APP-X",
        history=[],
        credentials=[],
        referees=[],
        verification_replies=[],
        verification_attempts=[],
        licence_lookup_wa=[],
        licence_lookup_other=[],
        certification_replies=[],
        peer_reference_replies=[],
        correspondence=[],
        as_of="2026-03-16",
        rules=RULES,
    )
    assert set(results.keys()) == {
        "licensure",
        "experience",
        "gaps",
        "education",
        "certification",
        "references",
    }


def test_resolve_references_escalates_after_max_attempts_with_no_reply():
    # rules.md documents the 3-attempts/21-days cadence as applying to references too (real
    # cases: REF-1401/APP-2026-014 and REF-2302/APP-2026-025 each logged attempts with no reply
    # yet) -- silence must not just sit as a generic "chase" message forever once attempts are
    # exhausted; it must say so, the same way education/experience already do.
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [{"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"}]
    attempts = [
        {"subject_ref": "REF-1", "element": "peer-reference", "attempt_date": "2026-01-01"},
        {"subject_ref": "REF-1", "element": "peer-reference", "attempt_date": "2026-01-22"},
        {"subject_ref": "REF-1", "element": "peer-reference", "attempt_date": "2026-02-12"},
    ]
    result = resolve_references(referees, replies, attempts, "2026-03-16", RULES)
    assert result.state == "outstanding"
    assert any("3 attempts" in item.item and "silence is not a pass" in item.item for item in result.action_items)


def test_resolve_references_chase_due_date_respects_min_spacing():
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [{"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"}]
    attempts = [{"subject_ref": "REF-1", "element": "peer-reference", "attempt_date": "2026-01-01"}]
    result = resolve_references(referees, replies, attempts, "2026-01-10", RULES)
    chase_items = [item for item in result.action_items if "REF-1" not in item.item or "Chase" in item.item]
    due_dates = [item.due for item in result.action_items if item.due]
    assert "2026-01-22" in due_dates


def test_resolve_attempt_tracked_element_accepts_confirmed_with_discrepancy():
    # Real case: VR-3002/APP-2026-030, outcome "confirmed-with-discrepancy" -- the source DID
    # reply (the discrepancy itself is handled separately by detect_discrepancies/the applicant
    # amending), so this must count as answered, not as silence. Without this, the entry can
    # never leave "outstanding" even after the applicant corrects the declared value to match.
    from scripts.engine import resolve_attempt_tracked_element

    history_entries = [{"entry_id": "ENT-1", "organization": "Mosswater Valley Hospital"}]
    verification_replies = [
        {"entry_id": "ENT-1", "element": "affiliation-and-employment", "outcome": "confirmed-with-discrepancy"}
    ]
    result = resolve_attempt_tracked_element(
        "experience", "affiliation-and-employment", history_entries, verification_replies, [], "2026-03-16", RULES
    )
    assert result.state == "resolved"
