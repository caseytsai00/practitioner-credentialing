from __future__ import annotations

from scripts.engine import admit_decision, compute_activation
from scripts.rules import load_rules
import os

RULES = load_rules(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "deliverables", "rules.md")
)


def _decision(**overrides):
    base = {
        "decision_id": "MEC-X",
        "body": "Executive Committee of the Medical Staff",
        "signatory": "Dr. Chair, MD",
        "role": "Chair",
        "outcome": "recommended",
    }
    base.update(overrides)
    return base


def test_executive_committee_recommendation_is_admitted():
    admitted, reason = admit_decision(_decision())
    assert admitted is True
    assert reason is None


def test_executive_committee_cannot_approve():
    admitted, reason = admit_decision(_decision(outcome="approved"))
    assert admitted is False
    assert "may not issue" in reason


def test_governing_body_approval_is_admitted():
    decision = _decision(body="Governing Body", outcome="approved", role="Chair, Governing Body")
    admitted, reason = admit_decision(decision)
    assert admitted is True


def test_decision_missing_signatory_is_refused():
    decision = _decision(signatory="")
    admitted, reason = admit_decision(decision)
    assert admitted is False
    assert "signatory" in reason


def test_unrecognized_body_is_refused():
    decision = _decision(body="Some Other Committee")
    admitted, reason = admit_decision(decision)
    assert admitted is False
    assert "not recognized" in reason


def test_duplicate_body_for_same_application_revision_is_refused():
    decision = _decision()
    admitted, reason = admit_decision(decision, already_admitted_bodies={"Executive Committee of the Medical Staff"})
    assert admitted is False
    assert "already admitted" in reason


def test_compute_activation_sets_two_year_cycle_and_active_flag():
    decision = _decision(
        body="Governing Body",
        outcome="approved",
        effective_date="2026-04-01",
        privileges=["PRIV-FM"],
    )
    activation = compute_activation(decision, RULES, as_of="2026-05-18")
    assert activation.effective_date == "2026-04-01"
    assert activation.cycle_end == "2028-04-01"
    assert activation.active_at_export is True
    assert activation.privileges == ["PRIV-FM"]


def test_compute_activation_not_active_before_effective_date():
    decision = _decision(
        body="Governing Body", outcome="approved", effective_date="2026-06-01", privileges=["PRIV-FM"]
    )
    activation = compute_activation(decision, RULES, as_of="2026-05-18")
    assert activation.active_at_export is False
