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


def test_apply_dispositions_resolves_a_finding_on_clear():
    elements = {name: "resolved" for name in ELEMENT_NAMES}
    elements["gaps"] = "finding"
    dispositions = [
        {
            "filename": "d1.md",
            "date": "2026-02-01",
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
            "raw_text": "The applicant does not meet the threshold criteria. Discontinue the application.",
        }
    ]
    _, status_override, action_items, _ = apply_dispositions(elements, dispositions)
    assert status_override == "discontinued"
    assert any("discontinuance" in item.item for item in action_items)


def test_apply_dispositions_unmatched_text_flags_for_human_interpretation():
    elements = {name: "resolved" for name in ELEMENT_NAMES}
    elements["licensure"] = "finding"
    dispositions = [{"filename": "d1.md", "date": "2026-02-01", "raw_text": "No recognized phrasing here."}]
    new_elements, status_override, action_items, unmatched = apply_dispositions(elements, dispositions)
    assert unmatched is True
    assert new_elements["licensure"] == "finding"
    assert any("could not be automatically interpreted" in item.item for item in action_items)


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
