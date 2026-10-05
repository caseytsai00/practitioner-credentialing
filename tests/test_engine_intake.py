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
        letters=[],
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
        letters=[],
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
        letters=[],
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
        letters=[],
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
        letters=[],
        as_of="2026-01-20",
        rules=RULES,
    )
    assert result.status == "returned-incomplete"
    assert result.clock_due is None


def test_privilege_request_citing_a_superseded_criteria_version_is_a_missing_item():
    # Interview, 05:23 PM: Renata shared "Privilege criteria — initial appointment
    # (LARK-PRIV-2026.1)" as the office's privilege criteria document; every privilege-requests.csv
    # row across all three real batches cites exactly this version. Intake completeness condition
    # 3 (02:14 PM) requires "a privilege request naming at least one group from the *current*
    # criteria" -- missing_intake_items previously only checked that a privilege request existed
    # at all, never that it actually cited the current version. No real case in the office's three
    # batches has a stale citation (every row cites LARK-PRIV-2026.1) -- synthetic, derived
    # directly from the interview's stated condition.
    result = evaluate_intake(
        application_id="APP-X",
        app_row=_complete_app_row(),
        disclosures=[],
        history=[],
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1", "criteria_version_cited": "LARK-PRIV-2024.1"}],
        referees=_two_referees(),
        correspondence=[],
        letters=[],
        as_of="2026-01-20",
        rules=RULES,
    )
    assert result.status == "intake-incomplete"
    assert any("current criteria" in item for item in result.missing_items)


def test_privilege_request_with_no_cited_version_is_not_penalized():
    # A blank/absent criteria_version_cited isn't evidence of a stale citation -- it's missing
    # data, and this condition (like the office's other data-derived completeness checks) treats
    # "we cannot tell" as satisfied rather than inventing a problem from an absent field. Every
    # other existing intake test's minimal fixture omits this field entirely; this confirms that
    # stays safe after the check above was added.
    result = evaluate_intake(
        application_id="APP-X",
        app_row=_complete_app_row(),
        disclosures=[{"answer": "No", "applicant_comment": ""}],
        history=[],
        credentials=[{"declaration_id": "DEC-1"}],
        priv_requests=[{"request_id": "REQ-1"}],
        referees=_two_referees(),
        correspondence=[],
        letters=[],
        as_of="2026-03-16",
        rules=RULES,
    )
    assert result.status == "complete"


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
    letters = [
        {
            "application_id": "APP-X",
            "letter_type": "gap-explanation",
            "date": "2026-01-05",
            "raw_text": "# Explanation of period 2020-06-02 to 2020-07-14\n\n**Period explained:** 2020-06-02 to 2020-07-14  \n\nI was travelling.",
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
        correspondence=[],
        letters=letters,
        as_of="2026-01-20",
        rules=RULES,
    )
    assert result.status == "complete"
