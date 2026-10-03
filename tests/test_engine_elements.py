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
    result = resolve_references(referees, replies, "2026-03-16", RULES)
    assert result.state == "resolved"


def test_resolve_references_excludes_related_or_partner_reply():
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [
        {"referee_id": "REF-1", "related_or_partner": "Yes", "signature_date": "2026-01-01"},
        {"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"},
    ]
    result = resolve_references(referees, replies, "2026-03-16", RULES)
    assert result.state == "outstanding"
    assert any("does not count" in item.item for item in result.action_items)


def test_resolve_references_stale_after_two_years_reverts_to_outstanding():
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [
        {"referee_id": "REF-1", "related_or_partner": "No", "signature_date": "2024-05-05"},
        {"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"},
    ]
    result = resolve_references(referees, replies, "2026-05-06", RULES)
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
