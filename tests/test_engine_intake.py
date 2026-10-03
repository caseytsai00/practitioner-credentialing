from __future__ import annotations

from scripts.engine import evaluate_intake
from scripts.rules import load_rules
import os

RULES = load_rules(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "deliverables", "rules.md")
)


def _complete_app_row():
    return {
        "application_id": "APP-X",
        "received_date": "2026-01-10",
        "release_signed_date": "2026-01-10",
        "cv_received_date": "2026-01-10",
    }


def _two_referees():
    return [
        {"referee_id": "REF-1", "application_id": "APP-X"},
        {"referee_id": "REF-2", "application_id": "APP-X"},
    ]


def test_complete_application_has_no_missing_items():
    result = evaluate_intake(
        application_id="APP-X",
        app_row=_complete_app_row(),
        disclosures=[{"answer": "No", "applicant_comment": ""}],
        history=[],
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1"}],
        referees=_two_referees(),
        correspondence=[],
        as_of="2026-03-16",
        rules=RULES,
    )
    assert result.status == "complete"
    assert result.missing_items == []


def test_missing_release_with_no_letter_yet_is_intake_incomplete_and_queues_a_letter():
    app_row = _complete_app_row()
    app_row["release_signed_date"] = ""
    result = evaluate_intake(
        application_id="APP-X",
        app_row=app_row,
        disclosures=[],
        history=[],
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1"}],
        referees=_two_referees(),
        correspondence=[],
        as_of="2026-01-20",
        rules=RULES,
    )
    assert result.status == "intake-incomplete"
    assert "Authorization and Release" in result.missing_items[0]
    assert "missing-items letter" in result.action_items[0].item
    assert result.action_items[0].owner == "Medical Services Professional"


def test_missing_items_within_clock_after_letter_sent_is_intake_incomplete_with_due_date():
    app_row = _complete_app_row()
    app_row["release_signed_date"] = ""
    correspondence = [
        {
            "application_id": "APP-X",
            "direction": "outbound",
            "date": "2026-01-20",
            "subject": "Missing items on your application",
        }
    ]
    result = evaluate_intake(
        application_id="APP-X",
        app_row=app_row,
        disclosures=[],
        history=[],
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1"}],
        referees=_two_referees(),
        correspondence=correspondence,
        as_of="2026-02-01",
        rules=RULES,
    )
    assert result.status == "intake-incomplete"
    assert result.clock_due == "2026-02-19"


def test_missing_items_after_clock_expires_is_ineligible_clock_expired():
    app_row = _complete_app_row()
    app_row["release_signed_date"] = ""
    correspondence = [
        {
            "application_id": "APP-X",
            "direction": "outbound",
            "date": "2026-01-20",
            "subject": "Missing items on your application",
        }
    ]
    result = evaluate_intake(
        application_id="APP-X",
        app_row=app_row,
        disclosures=[],
        history=[],
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1"}],
        referees=_two_referees(),
        correspondence=correspondence,
        as_of="2026-03-01",
        rules=RULES,
    )
    assert result.status == "ineligible-clock-expired"


def test_unexplained_30_day_gap_is_returned_incomplete_with_no_clock():
    history = [
        {
            "application_id": "APP-X",
            "entry_type": "employment",
            "from_date": "2020-01-01",
            "to_date": "2020-06-01",
            "contact_name": "Jo",
            "contact_email": "jo@example.com",
            "organization": "Org A",
        },
        {
            "application_id": "APP-X",
            "entry_type": "employment",
            "from_date": "2020-07-15",
            "to_date": "2026-01-01",
            "contact_name": "Jo",
            "contact_email": "jo@example.com",
            "organization": "Org B",
        },
    ]
    result = evaluate_intake(
        application_id="APP-X",
        app_row=_complete_app_row(),
        disclosures=[],
        history=history,
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1"}],
        referees=_two_referees(),
        correspondence=[],
        as_of="2026-01-20",
        rules=RULES,
    )
    assert result.status == "returned-incomplete"
    assert result.clock_due is None


def test_explained_gap_does_not_block_intake():
    history = [
        {
            "application_id": "APP-X",
            "entry_type": "employment",
            "from_date": "2020-01-01",
            "to_date": "2020-06-01",
            "contact_name": "Jo",
            "contact_email": "jo@example.com",
            "organization": "Org A",
        },
        {
            "application_id": "APP-X",
            "entry_type": "employment",
            "from_date": "2020-07-15",
            "to_date": "2026-01-01",
            "contact_name": "Jo",
            "contact_email": "jo@example.com",
            "organization": "Org B",
        },
    ]
    correspondence = [
        {
            "application_id": "APP-X",
            "direction": "inbound",
            "date": "2026-01-05",
            "subject": "Explanation of period 2020-06-02 to 2020-07-14",
        }
    ]
    result = evaluate_intake(
        application_id="APP-X",
        app_row=_complete_app_row(),
        disclosures=[],
        history=history,
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1"}],
        referees=_two_referees(),
        correspondence=correspondence,
        as_of="2026-01-20",
        rules=RULES,
    )
    assert result.status == "complete"
