from __future__ import annotations

from scripts.engine import admit_decision, compute_activation
from scripts.rules import load_rules
import os

RULES = load_rules(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "deliverables", "rules.md")
)

# Real signatories/roles/terms from docs/office-documents/LARK-AUTH-2026.1-reserved-authority.md,
# effective 2026-01-01. Every test below uses these real names rather than placeholders, since
# admit_decision now checks the decision's (body, signatory, role, decision_date) against this
# roster directly.


def _decision(**overrides):
    base = {
        "decision_id": "MEC-X",
        "body": "Executive Committee of the Medical Staff",
        "signatory": "Dr. Peter Vandermolen, MD",
        "role": "Chair, Executive Committee of the Medical Staff",
        "outcome": "recommended",
        "decision_date": "2026-03-10",
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


def test_governing_body_approval_by_chair_is_admitted():
    decision = _decision(
        body="Governing Body",
        outcome="approved",
        signatory="Ms. Corinne Batiste",
        role="Chair, Governing Body",
        decision_date="2026-04-14",
    )
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
        signatory="Ms. Corinne Batiste",
        role="Chair, Governing Body",
        effective_date="2026-04-01",
        decision_date="2026-04-01",
        privileges=["PRIV-FM"],
    )
    activation = compute_activation(decision, RULES, as_of="2026-05-18")
    assert activation.effective_date == "2026-04-01"
    assert activation.cycle_end == "2028-04-01"
    assert activation.active_at_export is True
    assert activation.privileges == ["PRIV-FM"]


def test_compute_activation_not_active_before_effective_date():
    decision = _decision(
        body="Governing Body", outcome="approved", signatory="Ms. Corinne Batiste", role="Chair, Governing Body",
        effective_date="2026-06-01", decision_date="2026-06-01", privileges=["PRIV-FM"],
    )
    activation = compute_activation(decision, RULES, as_of="2026-05-18")
    assert activation.active_at_export is False


# docs/office-documents/LARK-AUTH-2026.1-reserved-authority.md, "Who may record what" table and
# "Individual authority" table. The interview's session-decision note in rules.md previously said
# "the interview never covered the authority roster or decision-admission criteria" -- it did; this
# is the roster. Replaces the name-presence-only check with the real one.


def test_credentials_committee_recommendation_is_admitted():
    # LARK-AUTH's third body, never previously recognized by admit_decision at all (it would have
    # been refused as "not recognized" even for a legitimate recommendation). No real decision
    # document in office-exports/ is actually from the Credentials Committee (checked across all
    # three batches) -- synthetic, derived directly from the roster.
    decision = _decision(
        body="Credentials Committee",
        signatory="Dr. Anneke Thorvald, MD",
        role="Chair, Credentials Committee",
        outcome="recommended",
        decision_date="2026-03-10",
    )
    admitted, reason = admit_decision(decision)
    assert admitted is True


def test_credentials_committee_cannot_approve():
    decision = _decision(
        body="Credentials Committee",
        signatory="Dr. Anneke Thorvald, MD",
        role="Chair, Credentials Committee",
        outcome="approved",
        decision_date="2026-03-10",
    )
    admitted, reason = admit_decision(decision)
    assert admitted is False
    assert "may not issue" in reason


def test_right_body_but_signatory_not_on_the_roster_is_refused():
    # The manual, Section 12, and LARK-AUTH's own opening line: "A record's own claim of
    # authority is not evidence of it." A name that is not on the roster for that body at all
    # must be refused, not admitted on the strength of a plausible-looking role string.
    decision = _decision(signatory="Dr. Someone Else, MD")
    admitted, reason = admit_decision(decision)
    assert admitted is False
    assert "not recorded as" in reason


def test_right_individual_wrong_role_text_is_refused():
    # Right person, but the role string doesn't match what the roster actually records them as --
    # e.g. the Clinical Director (who has her own, separate reserved authority) signing as though
    # she holds a committee chair role she does not hold.
    decision = _decision(signatory="Dr. Marguerite Oyelaran, MD", role="Chair, Executive Committee of the Medical Staff")
    admitted, reason = admit_decision(decision)
    assert admitted is False
    assert "not recorded as" in reason


def test_governing_body_decision_by_vice_chair_within_2026_designation_is_admitted():
    # LARK-AUTH: "On 2026-01-05 the Chair of the Governing Body designated the Vice-Chair, Mr.
    # Desmond Ihejirika, to record credentialing approvals on her behalf for the calendar year
    # 2026." Real case: every Governing Body decision signed by the Vice-Chair across all three
    # batches falls in this window (checked: 2026-04-14 through 2026-05-12).
    decision = _decision(
        body="Governing Body",
        outcome="approved",
        signatory="Mr. Desmond Ihejirika",
        role="Vice-Chair, Governing Body",
        decision_date="2026-04-14",
    )
    admitted, reason = admit_decision(decision)
    assert admitted is True


def test_governing_body_decision_by_vice_chair_outside_2026_designation_is_refused():
    # The Vice-Chair's own term in the roster runs 2026-01-01 to 2026-12-31 -- the designation is
    # explicitly calendar-year-2026-only, not an ongoing authority. No real decision in the three
    # batches is dated outside 2026 (synthetic, derived directly from the roster's stated term).
    decision = _decision(
        body="Governing Body",
        outcome="approved",
        signatory="Mr. Desmond Ihejirika",
        role="Vice-Chair, Governing Body",
        decision_date="2027-01-15",
    )
    admitted, reason = admit_decision(decision)
    assert admitted is False
    assert "outside their term" in reason


def test_decision_with_no_decision_date_is_refused():
    # The roster check is "did that person hold that role on the decision date" -- with no date
    # to check, admission cannot be confirmed, so it is refused rather than assumed.
    decision = _decision(decision_date="")
    admitted, reason = admit_decision(decision)
    assert admitted is False
