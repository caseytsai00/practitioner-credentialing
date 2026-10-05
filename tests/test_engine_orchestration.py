from __future__ import annotations

import os

from scripts.engine import (
    apply_dispositions,
    merge_rows,
    parse_disposition_outcome,
    process_application,
    process_batch,
)
from scripts.model import ELEMENT_NAMES
from scripts.rules import load_rules
from scripts.state import new_ledger

RULES = load_rules(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "deliverables", "rules.md")
)


def test_merge_rows_overwrites_by_natural_key():
    existing = [{"entry_id": "ENT-1", "organization": "Old Co"}]
    new = [{"entry_id": "ENT-1", "organization": "New Co"}, {"entry_id": "ENT-2", "organization": "Other Co"}]
    merged = merge_rows(existing, new, "entry_id")
    by_id = {row["entry_id"]: row for row in merged}
    assert by_id["ENT-1"]["organization"] == "New Co"
    assert by_id["ENT-2"]["organization"] == "Other Co"
    assert len(merged) == 2


def test_parse_disposition_outcome_discontinue():
    text = "The applicant does not meet the threshold criteria. Discontinue the application and tell the applicant."
    assert parse_disposition_outcome(text) == {"discontinue"}


def test_parse_disposition_outcome_do_not_discontinue_is_not_discontinue():
    text = "Offer the applicant the opportunity to amend the privilege request. Do not discontinue the application."
    labels = parse_disposition_outcome(text)
    assert "discontinue" not in labels
    assert "amend-offer" in labels


def test_parse_disposition_outcome_clear_signals():
    text = "The explanation is sufficient and the file may proceed. I record no condition."
    assert parse_disposition_outcome(text) == {"clear"}


def test_parse_disposition_outcome_unmatched_text_is_empty_set():
    assert parse_disposition_outcome("Some unrelated note with no recognized phrasing.") == set()


# docs/office-documents/LARK-AUTH-2026.1-reserved-authority.md, "Individual authority" table:
# "Clinical Director | Dr. Marguerite Oyelaran, MD | 2025-07-01 to 2027-06-30 | Record a
# disposition on a gap explanation, on a high-risk or licensure finding, and on a threshold
# eligibility question; decide whether an application is discontinued." Real dispositions'
# "Recorded by:" field (scripts/parsers.py's recorded_by) always reads exactly
# "Dr. Marguerite Oyelaran, MD, Clinical Director" (confirmed across all 5 real disposition
# documents) -- the roster's signatory name followed by her role, comma-separated, matching the
# combined single-field format the office's own documents use (unlike decisions, which carry
# signatory and role as two separate fields).
_CLINICAL_DIRECTOR_RECORDED_BY = "Dr. Marguerite Oyelaran, MD, Clinical Director"


def test_apply_dispositions_resolves_a_finding_on_clear():
    elements = {name: "resolved" for name in ELEMENT_NAMES}
    elements["gaps"] = "finding"
    dispositions = [
        {
            "filename": "d1.md",
            "date": "2026-02-01",
            "recorded_by": _CLINICAL_DIRECTOR_RECORDED_BY,
            "raw_text": "The explanation is sufficient and the file may proceed.",
        }
    ]
    new_elements, status_override, action_items, unmatched = apply_dispositions(elements, dispositions)
    assert new_elements["gaps"] == "resolved"
    assert status_override is None
    assert unmatched is False


def test_apply_dispositions_discontinue_sets_status_override():
    elements = {name: "resolved" for name in ELEMENT_NAMES}
    elements["certification"] = "eligibility-question"
    dispositions = [
        {
            "filename": "d1.md",
            "date": "2026-02-01",
            "recorded_by": _CLINICAL_DIRECTOR_RECORDED_BY,
            "raw_text": "The applicant does not meet the threshold criteria. Discontinue the application.",
        }
    ]
    _, status_override, action_items, _ = apply_dispositions(elements, dispositions)
    assert status_override == "discontinued"
    assert any("discontinuance" in item.item for item in action_items)


def test_apply_dispositions_unmatched_text_flags_for_human_interpretation():
    elements = {name: "resolved" for name in ELEMENT_NAMES}
    elements["licensure"] = "finding"
    dispositions = [
        {
            "filename": "d1.md",
            "date": "2026-02-01",
            "recorded_by": _CLINICAL_DIRECTOR_RECORDED_BY,
            "raw_text": "No recognized phrasing here.",
        }
    ]
    new_elements, status_override, action_items, unmatched = apply_dispositions(elements, dispositions)
    assert unmatched is True
    assert new_elements["licensure"] == "finding"
    assert any("could not be automatically interpreted" in item.item for item in action_items)


def test_apply_dispositions_refuses_a_disposition_not_recorded_by_the_clinical_director():
    # LARK-AUTH-2026.1's opening line applies here exactly as it does to decisions: "A record's
    # own claim of authority is not evidence of it." A disposition recorded by anyone else must
    # not clear a finding, however well-phrased its text -- it is refused and raised to a human,
    # the same way an inadmissible decision is. No real disposition in office-exports/ is signed
    # by anyone but the Clinical Director (synthetic, derived directly from the roster).
    elements = {name: "resolved" for name in ELEMENT_NAMES}
    elements["gaps"] = "finding"
    dispositions = [
        {
            "filename": "d1.md",
            "date": "2026-02-01",
            "recorded_by": "Dr. Peter Vandermolen, MD, Chair, Executive Committee of the Medical Staff",
            "raw_text": "The explanation is sufficient and the file may proceed.",
        }
    ]
    new_elements, status_override, action_items, unmatched = apply_dispositions(elements, dispositions)
    assert new_elements["gaps"] == "finding"
    assert unmatched is True
    assert any("Clinical Director" in item.item for item in action_items)


def test_apply_dispositions_refuses_a_disposition_outside_the_clinical_directors_term():
    # LARK-AUTH-2026.1: Clinical Director's term is 2025-07-01 to 2027-06-30. A disposition dated
    # outside that window, even if correctly attributed by name and role, is refused.
    elements = {name: "resolved" for name in ELEMENT_NAMES}
    elements["gaps"] = "finding"
    dispositions = [
        {
            "filename": "d1.md",
            "date": "2024-01-15",
            "recorded_by": _CLINICAL_DIRECTOR_RECORDED_BY,
            "raw_text": "The explanation is sufficient and the file may proceed.",
        }
    ]
    new_elements, status_override, action_items, unmatched = apply_dispositions(elements, dispositions)
    assert new_elements["gaps"] == "finding"
    assert unmatched is True


class _FakeBatch:
    """A minimal stand-in for scripts.parsers.BatchData, built in memory for this test."""

    def __init__(self, **kwargs):
        defaults = dict(
            applications=[],
            disclosures=[],
            declared_history=[],
            declared_credentials=[],
            privilege_requests=[],
            peer_referees=[],
            verification_replies=[],
            verification_attempts=[],
            certification_replies=[],
            peer_reference_replies=[],
            correspondence=[],
            licence_lookup_wa=[],
            licence_lookup_other=[],
            letters={},
            decisions={},
            dispositions={},
        )
        defaults.update(kwargs)
        for key, value in defaults.items():
            setattr(self, key, value)

    def application_ids(self):
        return sorted({row["application_id"] for row in self.applications})

    def decision_filenames(self):
        return sorted(d["filename"] for d in self.decisions.values())


def _complete_minimal_batch(application_id="APP-X", revision="1", org="Test Clinic"):
    # Two contiguous declared-history entries (residency ending exactly where employment starts,
    # so there is no gap to trip the 30-day gap-return logic) -- one maps to "education", one to
    # "experience" -- plus a licence and a certification credential, so every one of the six
    # elements has something to resolve. Without the residency entry, "education" would have
    # nothing to verify and stay outstanding forever; without the certification credential,
    # "certification" would too -- both are needed to actually reach packet-presentable below.
    return _FakeBatch(
        applications=[
            {
                "application_id": application_id,
                "revision": revision,
                "received_date": "2026-01-10",
                "release_signed_date": "2026-01-10",
                "cv_received_date": "2026-01-10",
            }
        ],
        declared_history=[
            {
                "entry_id": "ENT-EDU",
                "application_id": application_id,
                "revision": revision,
                "entry_type": "residency",
                "organization": "Test Residency Hospital",
                "role": "Family Medicine Residency",
                "from_date": "2010-07-01",
                "to_date": "2013-06-30",
                "contact_name": "Ed Reg",
                "contact_email": "ed@example.com",
            },
            {
                "entry_id": "ENT-1",
                "application_id": application_id,
                "revision": revision,
                "entry_type": "employment",
                "organization": org,
                "from_date": "2013-07-01",
                "to_date": "2026-01-01",
                "contact_name": "Jo",
                "contact_email": "jo@example.com",
            },
        ],
        declared_credentials=[
            {
                "application_id": application_id,
                "revision": revision,
                "declaration_id": "DEC-1",
                "credential_class": "licence",
                "number_declared": "MD1",
            },
            {
                "application_id": application_id,
                "revision": revision,
                "declaration_id": "DEC-2",
                "credential_class": "certification",
                "issuer": "American Board of Family Medicine",
            },
        ],
        privilege_requests=[
            {"application_id": application_id, "revision": revision, "request_id": "REQ-1", "privilege_name": "Family Medicine"}
        ],
        peer_referees=[
            {"application_id": application_id, "revision": revision, "referee_id": "REF-1", "referee_name": "A"},
            {"application_id": application_id, "revision": revision, "referee_id": "REF-2", "referee_name": "B"},
        ],
        verification_replies=[
            {
                "application_id": application_id,
                "entry_id": "ENT-EDU",
                "reply_id": "VR-EDU",
                "element": "education-and-training",
                "outcome": "confirmed",
            },
            {
                "application_id": application_id,
                "entry_id": "ENT-1",
                "reply_id": "VR-1",
                "element": "affiliation-and-employment",
                "outcome": "confirmed",
            },
        ],
        certification_replies=[
            {
                "application_id": application_id,
                "reply_id": "CR-1",
                "declaration_id": "DEC-2",
                "received_date": "2026-01-20",
                "certification_status": "Active",
            }
        ],
        peer_reference_replies=[
            {
                "application_id": application_id,
                "referee_id": "REF-1",
                "reply_id": "RR-1",
                "related_or_partner": "No",
                "signature_date": "2026-01-15",
            },
            {
                "application_id": application_id,
                "referee_id": "REF-2",
                "reply_id": "RR-2",
                "related_or_partner": "No",
                "signature_date": "2026-01-16",
            },
        ],
        licence_lookup_wa=[
            {"credentialnumber": "MD1", "status": "ACTIVE", "expirationdate": "2030-01-01", "actiontaken": "No"}
        ],
    )


def test_process_application_reaches_packet_presentable_when_everything_resolves():
    batch = _complete_minimal_batch()
    ledger = new_ledger()
    # process_application assumes the global licence-lookup tables were already merged into the
    # ledger -- that merge normally happens once per batch, at the top of process_batch (licence
    # lookups carry no application_id, so they can't be merged per-application). This test calls
    # process_application directly, so it seeds that merge itself.
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert warnings == []
    assert record.status == "packet-presentable"
    assert record.packet_presentable is True
    assert all(state == "resolved" for state in record.elements.values())


def test_process_batch_resumes_and_a_correction_does_not_disturb_unrelated_elements():
    ledger = new_ledger()
    batch_one = _complete_minimal_batch(org="Willowmere Health Cooperative")
    records_one, ledger, warnings_one = process_batch(batch_one, ledger, RULES, "2026-03-16")
    assert warnings_one == []
    app_one = next(r for r in records_one if r.application_id == "APP-X")
    assert app_one.elements["licensure"] == "resolved"
    assert app_one.elements["experience"] == "resolved"

    # Batch two: same application, revision 2, ONLY the employer name corrected (entry_id reused).
    batch_two = _complete_minimal_batch(revision="2", org="Silverbeck Physicians Group")
    # The correction restates the verification reply too (still confirmed) and the application row,
    # but NOT the licence credential or lookup -- those simply aren't touched this batch.
    batch_two.declared_credentials = []
    batch_two.licence_lookup_wa = []
    batch_two.peer_referees = []
    batch_two.peer_reference_replies = []
    batch_two.privilege_requests = []

    records_two, ledger, warnings_two = process_batch(batch_two, ledger, RULES, "2026-04-20")
    assert warnings_two == []
    app_two = next(r for r in records_two if r.application_id == "APP-X")
    assert app_two.revision == 2
    # Licensure and references never appeared in batch two at all -- they must still read resolved
    # from the ledger's carried-forward accumulated rows, proving the correction didn't disturb them.
    assert app_two.elements["licensure"] == "resolved"
    assert app_two.elements["references"] == "resolved"
    assert app_two.elements["experience"] == "resolved"
    assert app_two.status == "packet-presentable"


def test_process_batch_withdrawal_is_sticky_and_quiet():
    ledger = new_ledger()
    batch_one = _complete_minimal_batch()
    records_one, ledger, _ = process_batch(batch_one, ledger, RULES, "2026-03-16")
    assert next(r for r in records_one if r.application_id == "APP-X").status == "packet-presentable"

    batch_two = _complete_minimal_batch(revision="1")
    batch_two.letters = {
        "2026-04-01_withdrawal_APP-X.md": {
            "filename": "2026-04-01_withdrawal_APP-X.md",
            "date": "2026-04-01",
            "letter_type": "withdrawal",
            "application_id": "APP-X",
            "raw_text": "I am withdrawing my application.",
        }
    }
    records_two, ledger, _ = process_batch(batch_two, ledger, RULES, "2026-04-20")
    app_two = next(r for r in records_two if r.application_id == "APP-X")
    assert app_two.status == "withdrawn"
    assert app_two.action_queue == []

    batch_three = _complete_minimal_batch(revision="1")
    batch_three.letters = {}
    records_three, ledger, _ = process_batch(batch_three, ledger, RULES, "2026-05-18")
    app_three = next(r for r in records_three if r.application_id == "APP-X")
    assert app_three.status == "withdrawn"


def test_admitted_governing_body_approval_governs_status_even_with_a_lingering_finding():
    # Real batch-02/03 data surfaced this: a Governing Body decision can admit an approval for a
    # revision while one of the six elements still shows "finding" in this engine's own tracking
    # (e.g. a certification lapse disposition that never explicitly cleared it). The admitted
    # decision is the office's real authority and must govern the status; a lingering finding the
    # Skill itself still has open belongs in the action queue, not in blocking the status at
    # "in-verification" forever.
    batch = _complete_minimal_batch()
    batch.certification_replies = [
        {
            "application_id": "APP-X",
            "reply_id": "CR-1",
            "declaration_id": "DEC-2",
            "received_date": "2026-01-20",
            "certification_status": "Lapsed",
        }
    ]
    batch.decisions = {
        "GBD-X": {
            "decision_id": "GBD-X",
            "body": "Governing Body",
            "signatory": "Ms. Corinne Batiste",
            "role": "Chair, Governing Body",
            "application_id": "APP-X",
            "revision": 1,
            "decision_date": "2026-02-01",
            "outcome": "approved",
            "privileges": ["PRIV-FM"],
            "criteria_version": "LARK-PRIV-2026.1",
            "reason": None,
            "effective_date": "2026-02-01",
            "supersedes": None,
            "filename": "d.md",
        }
    }
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert record.elements["certification"] == "finding"
    assert record.approval_decision_id == "GBD-X"
    assert record.status == "active"


def test_decision_for_a_superseded_revision_is_refused_not_silently_dropped():
    # Real data: APP-2026-036 had a Governing Body approval admitted for revision 1, then an
    # unrelated correction (an employer name fix) bumped the file to revision 2 in the same
    # batch. The decision must not vanish from decisions[] -- it must show up refused, with a
    # reason, and queue a human to confirm whether it still stands.
    batch = _complete_minimal_batch(revision="2")
    batch.decisions = {
        "GBD-X": {
            "decision_id": "GBD-X",
            "body": "Governing Body",
            "signatory": "Ms. Corinne Batiste",
            "role": "Chair, Governing Body",
            "application_id": "APP-X",
            "revision": 1,
            "decision_date": "2026-02-01",
            "outcome": "approved",
            "privileges": ["PRIV-FM"],
            "criteria_version": "LARK-PRIV-2026.1",
            "reason": None,
            "effective_date": "2026-02-01",
            "supersedes": None,
            "filename": "d.md",
        }
    }
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    decision_ids = {d.decision_id: d for d in record.decisions}
    assert "GBD-X" in decision_ids
    assert decision_ids["GBD-X"].admitted is False
    assert "revision" in decision_ids["GBD-X"].reason
    assert record.approval_decision_id is None
    assert any("GBD-X" in item.item for item in record.action_queue)


def test_ppq_yes_disclosure_forces_a_finding_even_when_otherwise_resolved():
    # Real data: APP-2026-032 answered PPQ-2 "Yes" with an explanation (satisfying intake) --
    # the office's real disposition calls this a "High-risk finding" needing Clinical Director
    # review. Nothing about the six elements themselves would otherwise flag it once licensure,
    # certification, etc. all independently resolve, so this must be its own, explicit check.
    batch = _complete_minimal_batch()
    batch.disclosures = [
        {
            "application_id": "APP-X",
            "revision": "1",
            "question_code": "PPQ-2",
            "answer": "Yes",
            "applicant_comment": "Explained in attached letter.",
        }
    ]
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert record.elements["licensure"] == "finding"
    assert record.status == "in-verification"
    assert any("PPQ" in item.item or "professional practice question" in item.item for item in record.action_queue)

    # Once a Clinical Director disposition clears it, the finding resolves and status can advance.
    batch_two = _complete_minimal_batch(revision="1")
    batch_two.disclosures = batch.disclosures
    batch_two.dispositions = {
        "d.md": {
            "filename": "d.md",
            "application_id": "APP-X",
            "date": "2026-02-01",
            "recorded_by": _CLINICAL_DIRECTOR_RECORDED_BY,
            "raw_text": "I record no bar to appointment and no condition.",
        }
    }
    record_two, warnings_two = process_application("APP-X", batch_two, ledger, RULES, "2026-04-20")
    assert record_two.elements["licensure"] == "resolved"
    assert record_two.status == "packet-presentable"


def test_parse_disposition_outcome_present_to_committee_alone_is_not_clear():
    # Real case: office-exports/batch-03/dispositions/2026-05-06_disposition_APP-2026-015.md --
    # the Clinical Director explicitly declines to clear the restriction ("not full and
    # unrestricted ... I make no recommendation on the privileges themselves") while still
    # routing the file onward. "Present the file to the committee" is an instruction to proceed
    # WITH the finding attached, not a determination that it's immaterial -- treating it as
    # "clear" lets the engine decide protected judgment #2 (whether a finding is disqualifying).
    text = (
        "The credential is current but it is not full and unrestricted while the stipulated "
        "agreement is in force. Present the file to the Executive Committee of the Medical Staff "
        "and the Governing Body with the board's summary attached. Do not discontinue the "
        "application. I make no recommendation on the privileges themselves."
    )
    labels = parse_disposition_outcome(text)
    assert "clear" not in labels
    assert "discontinue" not in labels


def test_parse_disposition_outcome_still_clears_when_no_bar_is_stated():
    # The office's own "present to committee" + "no bar to appointment" combination (real case:
    # APP-2026-032) must still resolve -- only the bare "present to committee" phrase alone,
    # with no actual determination, must stop being treated as clearing.
    text = (
        "Present the file to the Executive Committee of the Medical Staff and the Governing Body "
        "with both documents attached. I record no bar to appointment and no condition."
    )
    assert "clear" in parse_disposition_outcome(text)


def test_extract_monitored_conditions_includes_approved_with_conditions_decision():
    from scripts.engine import extract_monitored_conditions

    store = {"letters": []}
    activation_decision = {
        "decision_id": "GBD-X",
        "outcome": "approved-with-conditions",
        "conditions": [
            {"condition": "Re-verification of the Washington licence", "due": "2026-11-30"},
            {"condition": "The Clinical Director's written concurrence", "due": "2026-06-30"},
        ],
    }
    conditions = [c.to_dict() for c in extract_monitored_conditions(store, activation_decision)]
    assert {"condition": "Re-verification of the Washington licence", "due": "2026-11-30"} in conditions
    assert {"condition": "The Clinical Director's written concurrence", "due": "2026-06-30"} in conditions


def test_approved_with_conditions_status_carries_its_own_conditions():
    # End-to-end: an admitted approved-with-conditions decision's Conditions block must show up
    # in the sealed record's monitored_conditions, not just in status.
    batch = _complete_minimal_batch()
    batch.decisions = {
        "GBD-X": {
            "decision_id": "GBD-X",
            "body": "Governing Body",
            "signatory": "Ms. Corinne Batiste",
            "role": "Chair, Governing Body",
            "application_id": "APP-X",
            "revision": 1,
            "decision_date": "2026-02-01",
            "outcome": "approved-with-conditions",
            "privileges": ["PRIV-FM"],
            "criteria_version": "LARK-PRIV-2026.1",
            "reason": None,
            "effective_date": "2026-02-01",
            "supersedes": None,
            "conditions": [{"condition": "Annual CME due", "due": "2027-02-01"}],
            "filename": "d.md",
        }
    }
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert record.status == "active-with-conditions"
    assert any(mc.condition == "Annual CME due" and mc.due == "2027-02-01" for mc in record.monitored_conditions)


def _gb_decision(decision_id, outcome, decision_date, reason=None, effective_date=None, revision=1):
    return {
        "decision_id": decision_id,
        "body": "Governing Body",
        "signatory": "Ms. Corinne Batiste",
        "role": "Chair, Governing Body",
        "application_id": "APP-X",
        "revision": revision,
        "decision_date": decision_date,
        "outcome": outcome,
        "privileges": ["PRIV-FM"],
        "criteria_version": "LARK-PRIV-2026.1",
        "reason": reason,
        "effective_date": effective_date,
        "supersedes": None,
        "conditions": [],
        "filename": decision_id + ".md",
    }


def test_a_later_decision_from_the_same_body_supersedes_an_earlier_one_rather_than_duplicate_refusal():
    # Real-world shape: a Governing Body defers, then later -- after the applicant supplies what
    # was missing -- the Governing Body approves. The earlier decision must not block the later,
    # legitimate one as a "duplicate": the later one is the operative decision; the earlier one
    # is refused as superseded by it, not as an inadmissible duplicate.
    batch = _complete_minimal_batch()
    batch.decisions = {
        "GBD-1": _gb_decision("GBD-1", "deferred-pending-information", "2026-02-01", reason="Needs one more reference."),
        "GBD-2": _gb_decision("GBD-2", "approved", "2026-02-15", effective_date="2026-02-15"),
    }
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    decisions_by_id = {d.decision_id: d for d in record.decisions}
    assert decisions_by_id["GBD-2"].admitted is True
    assert decisions_by_id["GBD-1"].admitted is False
    assert "superseded" in decisions_by_id["GBD-1"].reason
    assert record.approval_decision_id == "GBD-2"


def test_a_refused_decision_for_any_reason_queues_a_human_action_item():
    # Real case: MEC-2026-036, Executive Committee issuing "approved" (only Governing Body may).
    # Any refusal -- not just a revision mismatch -- leaves a file that needs a human's attention
    # to get the decision reissued correctly; action_queue must never silently stay empty for it.
    batch = _complete_minimal_batch()
    batch.decisions = {
        "MEC-X": {
            "decision_id": "MEC-X",
            "body": "Executive Committee of the Medical Staff",
            "signatory": "Dr. Chair, MD",
            "role": "Chair",
            "application_id": "APP-X",
            "revision": 1,
            "decision_date": "2026-02-01",
            "outcome": "approved",
            "privileges": ["PRIV-FM"],
            "criteria_version": "LARK-PRIV-2026.1",
            "reason": None,
            "effective_date": None,
            "supersedes": None,
            "conditions": [],
            "filename": "MEC-X.md",
        }
    }
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert any(d.decision_id == "MEC-X" and d.admitted is False for d in record.decisions)
    assert any("MEC-X" in item.item for item in record.action_queue)


def test_deferred_decisions_reason_is_surfaced_to_the_action_queue():
    # Real case: APP-2026-034, deferred pending one further peer reference "from a referee
    # outside the applicant's current group practice" -- a file on a Governing Body hold must
    # name what's owed, not sit with an empty action_queue.
    batch = _complete_minimal_batch()
    batch.decisions = {
        "GBD-1": _gb_decision(
            "GBD-1",
            "deferred-pending-information",
            "2026-02-01",
            reason="Needs one further peer reference from a referee outside the applicant's current group practice.",
        )
    }
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, warnings = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert record.status == "deferred"
    assert any("referee outside" in item.item for item in record.action_queue)


def test_discontinued_application_keeps_its_notify_action_item_in_a_later_batch():
    # Real case: APP-2026-029's "Notify applicant of discontinuance ..." action item is present
    # in the batch it was discovered but vanishes in the next batch, because the sticky
    # terminal-state short-circuit doesn't carry it forward. Once discontinued, the record a
    # reader sees later must still show what was done, not silently go quiet.
    batch_one = _complete_minimal_batch()
    batch_one.dispositions = {
        "d.md": {
            "filename": "d.md",
            "application_id": "APP-X",
            "date": "2026-02-01",
            "recorded_by": _CLINICAL_DIRECTOR_RECORDED_BY,
            "raw_text": "Discontinue the application and tell the applicant.",
        }
    }
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch_one.licence_lookup_wa)
    record_one, _ = process_application("APP-X", batch_one, ledger, RULES, "2026-03-16")
    assert record_one.status == "discontinued"
    assert any("Notify applicant of discontinuance" in item.item for item in record_one.action_queue)

    batch_two = _complete_minimal_batch(revision="1")
    batch_two.dispositions = {}
    record_two, _ = process_application("APP-X", batch_two, ledger, RULES, "2026-04-20")
    assert record_two.status == "discontinued"
    assert any("Notify applicant of discontinuance" in item.item for item in record_two.action_queue)


def test_eligibility_mismatch_does_not_clobber_an_existing_certification_finding():
    # Real-shaped combination of two independently real patterns: APP-2026-027's inactive
    # certification (resolve_certification -> `finding`) and APP-2026-029's unsupported privilege
    # request (detect_eligibility_mismatch -> `eligibility-question`). Both already happen in the
    # real data separately; nothing stops them from coinciding on the same file. Before this fix,
    # detect_eligibility_mismatch unconditionally overwrote `elements["certification"]`, so a real
    # board-reported inactive certification would silently vanish from the sealed `elements` dict
    # the moment an unrelated eligibility mismatch was also detected -- even though
    # resolve_certification's own action item (routed to the Clinical Director) stayed in the
    # queue the whole time. The element state must reflect whichever concern was found first, not
    # whichever check happened to run last; both action items must still appear either way.
    batch = _complete_minimal_batch()
    batch.certification_replies = [
        {
            "application_id": "APP-X",
            "reply_id": "CR-1",
            "declaration_id": "DEC-2",
            "received_date": "2026-01-20",
            "certification_status": "Inactive",
            "board_name": "American Board of Family Medicine",
        }
    ]
    batch.privilege_requests = [
        {"application_id": "APP-X", "revision": "1", "request_id": "REQ-1", "privilege_code": "PRIV-ORTHO", "privilege_name": "Orthopaedic Surgery"}
    ]
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, _ = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert record.elements["certification"] == "finding"
    assert any("shows status 'Inactive'" in item.item for item in record.action_queue)
    assert any("Nothing on file supports the privilege requested" in item.item for item in record.action_queue)


def test_ppq_finding_does_not_clobber_an_existing_licensure_discrepancy():
    # Mirror of the certification/eligibility-mismatch case above, for the identical pattern on
    # licensure: detect_ppq_findings unconditionally overwrote `elements["licensure"]` too, so a
    # real credential discrepancy (declared_issue_date mismatch, added for edge case #4) would
    # silently vanish from the sealed `elements` dict the moment an unrelated PPQ "Yes" answer was
    # also present -- even though the Applicant-owned discrepancy action item stayed in the queue
    # the whole time with a different owner than the PPQ finding's Clinical-Director item.
    batch = _complete_minimal_batch()
    batch.declared_credentials[0]["declared_issue_date"] = "2010-01-01"
    batch.licence_lookup_wa = [
        {
            "credentialnumber": "MD1",
            "status": "ACTIVE",
            "expirationdate": "2030-01-01",
            "actiontaken": "No",
            "firstissuedate": "2012-06-30",
        }
    ]
    batch.disclosures = [
        {
            "application_id": "APP-X",
            "revision": "1",
            "question_code": "PPQ-2",
            "answer": "Yes",
            "applicant_comment": "Explained in attached letter.",
        }
    ]
    ledger = new_ledger()
    ledger["licence_lookup_wa"] = list(batch.licence_lookup_wa)
    record, _ = process_application("APP-X", batch, ledger, RULES, "2026-03-16")
    assert record.elements["licensure"] == "discrepancy"
    assert any("Discrepancy on DEC-1" in item.item and item.owner == "Applicant" for item in record.action_queue)
    assert any("professional practice question" in item.item and item.owner == "Clinical Director" for item in record.action_queue)
