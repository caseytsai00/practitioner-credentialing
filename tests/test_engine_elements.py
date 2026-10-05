from __future__ import annotations

from scripts.engine import (
    resolve_attempt_tracked_element,
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


def test_resolve_licensure_wa_joins_by_name_and_birthyear_not_declared_number():
    # office-note-2026-03-16-export-format.md: "The Washington board export carries no
    # practitioner identifier... I join it to an application on lastname, firstname, middlename
    # and birthyear." A declared number that doesn't match the WA lookup's own credentialnumber
    # must not block the match when the applicant's name and birth year do.
    credentials = [{"credential_class": "licence", "jurisdiction_or_board": "WA", "number_declared": "MD-TYPO"}]
    lookup_wa = [
        {"credentialnumber": "MD60000001", "status": "ACTIVE", "expirationdate": "2030-01-01", "actiontaken": "No",
         "lastname": "Holloway", "firstname": "Marcus", "middlename": "T", "birthyear": "1982"}
    ]
    app_row = {"last_name": "Holloway", "first_name": "Marcus", "middle_name": "T", "birth_year": "1982"}
    result = resolve_licensure(credentials, lookup_wa, [], "2026-03-16", app_row=app_row)
    assert result.state == "resolved"


def test_resolve_licensure_wa_absence_is_confirmed_not_unresolved():
    # office-note: "An applicant with no row in that file holds no Washington credential. The
    # absence is the answer, not a data problem." The action item must reflect that, not read as
    # though more data might still turn up.
    credentials = [{"credential_class": "licence", "jurisdiction_or_board": "WA", "number_declared": "MD60000001"}]
    app_row = {"last_name": "NoSuchPerson", "first_name": "X", "middle_name": "", "birth_year": "1900"}
    result = resolve_licensure(credentials, [], [], "2026-03-16", app_row=app_row)
    assert result.state == "outstanding"
    assert any("confirmed absent" in item.item for item in result.action_items)


def test_resolve_certification_resolved_when_active_reply_on_file():
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "ABFM"}]
    replies = [{"declaration_id": "DEC-1", "received_date": "2026-02-01", "certification_status": "Active"}]
    result = resolve_certification(credentials, replies, "2026-03-16")
    assert result.state == "resolved"


def test_resolve_certification_finding_when_inactive():
    # Real case: CR-02700/APP-2026-027 -- the American Board of Surgery reports status
    # "Inactive" (office-exports/batch-01/certification-replies.csv). "Lapsed" never appears as
    # a certification_status value anywhere in the office's data -- the real taxonomy across all
    # three batches is Active/Inactive/Not certified -- so the fixture uses a real observed
    # value instead of an invented one that happens to not match the code's allow-list.
    credentials = [
        {"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "American Board of Surgery"}
    ]
    replies = [{"declaration_id": "DEC-1", "received_date": "2026-02-01", "certification_status": "Inactive"}]
    result = resolve_certification(credentials, replies, "2026-03-16")
    assert result.state == "finding"


def test_resolve_certification_accepts_a_designated_equivalent_board():
    # docs/office-documents/LARK-ATT-2026.1-accepted-sources.md, "Board certification" table,
    # "Designated equivalent source" row: CertiFACTS is admissible by name even though it will
    # never match the declared issuing board's own name. No real case in office-exports/ exercises
    # this (every certification-replies.csv row across all three batches comes directly from the
    # issuing board itself), so this is a synthetic test derived directly from the table, not from
    # any observed data -- flagged as such rather than presented as a real-case regression.
    credentials = [
        {"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "American Board of Family Medicine"}
    ]
    replies = [
        {
            "declaration_id": "DEC-1",
            "received_date": "2026-02-01",
            "certification_status": "Active",
            "board_name": "CertiFACTS",
        }
    ]
    result = resolve_certification(credentials, replies, "2026-03-16")
    assert result.state == "resolved"


def test_resolve_certification_inadmissible_source_stays_outstanding_not_finding():
    # docs/office-documents/LARK-ATT-2026.1-accepted-sources.md, "Board certification" table,
    # "Not accepted" row: "A specialty society membership roster" is explicitly not an accepted
    # source, regardless of what status it reports. Per "What to do with a reply that is not on
    # this table": "Mark the entry still outstanding" -- not `finding`, since `finding` means a
    # real, trusted determination the Clinical Director must judge, and an inadmissible reply is
    # not evidence the Skill may trust at all. No real case in the data exercises this (synthetic,
    # derived directly from the table).
    credentials = [
        {"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "American Board of Family Medicine"}
    ]
    replies = [
        {
            "declaration_id": "DEC-1",
            "received_date": "2026-02-01",
            "certification_status": "Active",
            "board_name": "State Family Medicine Society membership roster",
        }
    ]
    result = resolve_certification(credentials, replies, "2026-03-16")
    assert result.state == "outstanding"
    assert any(
        "not on the accepted-sources table" in item.item and "Medical Services Professional" in item.item
        for item in result.action_items
    )


def test_resolve_certification_expired_reverts_to_outstanding():
    # Interview, opening remarks, 07:13 PM: "a file sits ready for the committee for weeks while
    # a licence expires underneath it or a peer reference passes its two-year signature date, and
    # I only notice when I happen to look." resolve_licensure already re-checks its expiry
    # against as_of on every run (it never trusted a stale "ACTIVE" status alone); this is the
    # same check for certification, which never had it. A certification_status of "Active" only
    # reflects what the board said when it replied -- it must not outlive its own expiry_date.
    # No real case in the office's three batches has an expiry_date before any batch's as_of
    # (checked across all certification-replies.csv rows) -- synthetic, derived directly from the
    # interview's own stated scenario.
    credentials = [
        {"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "American Board of Family Medicine"}
    ]
    replies = [
        {
            "declaration_id": "DEC-1",
            "received_date": "2026-02-01",
            "certification_status": "Active",
            "board_name": "American Board of Family Medicine",
            "expiry_date": "2026-03-01",
        }
    ]
    result = resolve_certification(credentials, replies, "2026-04-20")
    assert result.state == "outstanding"
    assert any(
        "expired" in item.item and "2026-03-01" in item.item and item.owner == "Medical Services Professional"
        for item in result.action_items
    )


def test_resolve_certification_not_yet_expired_still_resolves():
    credentials = [
        {"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "American Board of Family Medicine"}
    ]
    replies = [
        {
            "declaration_id": "DEC-1",
            "received_date": "2026-02-01",
            "certification_status": "Active",
            "board_name": "American Board of Family Medicine",
            "expiry_date": "2030-12-31",
        }
    ]
    result = resolve_certification(credentials, replies, "2026-04-20")
    assert result.state == "resolved"


def test_resolve_certification_blank_expiry_date_never_expires():
    # office-note-2026-03-16-export-format.md: "a blank expiry_date in certification-replies.csv
    # means the certificate does not expire -- some older certificates are time-unlimited." A
    # blank must never be treated as unknown/missing-therefore-flagged data; it's a specific,
    # affirmative fact. Real case: CR-01000/APP-2026-010 has a blank expiry_date (status "Not
    # certified", so it never reaches this check in practice) -- this test exercises the Active
    # path directly since no real row combines a blank expiry with an Active status.
    credentials = [
        {"credential_class": "certification", "declaration_id": "DEC-1", "issuer": "American Board of Family Medicine"}
    ]
    replies = [
        {
            "declaration_id": "DEC-1",
            "received_date": "2020-01-01",
            "certification_status": "Active",
            "board_name": "American Board of Family Medicine",
            "expiry_date": "",
        }
    ]
    result = resolve_certification(credentials, replies, "2026-04-20")
    assert result.state == "resolved"


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


def test_resolve_references_currency_measured_against_governing_body_presentation_not_as_of():
    # docs/office-documents/LARK-REF-2026.1-peer-reference-form.md, "Currency": "A reference is
    # current if the signature date is within two years of the date the file is presented to the
    # Governing Body... not the date we receive the form" -- and not the batch's export date
    # either, which previously drove this check. A signature dated just under two years before
    # the (earlier) Governing Body presentation date must read current, even when the batch's
    # as_of is well past the two-year mark -- the file isn't waiting on a stale reference; the
    # reference was current when it mattered, and a later batch recomputing with a newer as_of
    # must not retroactively make it stale.
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [
        {"referee_id": "REF-1", "related_or_partner": "No", "signature_date": "2024-05-05"},
        {"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2024-05-06"},
    ]
    result = resolve_references(referees, replies, [], "2026-05-06", RULES, currency_date="2026-04-14")
    assert result.state == "resolved"


def test_resolve_references_currency_falls_back_to_as_of_with_no_governing_body_date_yet():
    # Before any Governing Body decision exists for this revision, there is no presentation date
    # to measure against -- as_of is the best available stand-in, matching prior behavior.
    referees = [{"referee_id": "REF-1", "referee_name": "A"}, {"referee_id": "REF-2", "referee_name": "B"}]
    replies = [
        {"referee_id": "REF-1", "related_or_partner": "No", "signature_date": "2024-05-05"},
        {"referee_id": "REF-2", "related_or_partner": "No", "signature_date": "2026-01-02"},
    ]
    result = resolve_references(referees, replies, [], "2026-05-06", RULES, currency_date=None)
    assert result.state == "outstanding"


def test_resolve_gaps_resolved_when_no_qualifying_gap():
    result = resolve_gaps("APP-X", [], [], RULES)
    assert result.state == "resolved"


def test_resolve_gaps_finding_when_explained_gap_awaits_cd_judgment():
    history = [
        {"from_date": "2020-01-01", "to_date": "2020-06-01"},
        {"from_date": "2020-07-15", "to_date": "2026-01-01"},
    ]
    letters = [
        {
            "application_id": "APP-X",
            "letter_type": "gap-explanation",
            "raw_text": "# Explanation of period 2020-06-02 to 2020-07-14\n\n**Period explained:** 2020-06-02 to 2020-07-14  \n\nI was travelling.",
        }
    ]
    result = resolve_gaps("APP-X", history, letters, RULES)
    assert result.state == "finding"
    assert result.evidence["gap_from"] == "2020-06-02"
    assert result.evidence["gap_to"] == "2020-07-14"


def test_resolve_gaps_requires_exact_match_to_the_letters_own_stated_dates():
    # LARK-APP-2026.1, Section F: "...the office matches your explanation to the period by those
    # two dates and by nothing else." A letter explaining a DIFFERENT (even overlapping) period
    # must not count -- matching used to be substring-containment against correspondence.csv's
    # own summary `subject` field (an office-authored index, not the applicant's letter), which
    # could be fooled by an unrelated letter whose subject happened to contain both date strings.
    # Here the letter's own **Period explained:** line names a period one day short of the real
    # gap at each end.
    history = [
        {"from_date": "2020-01-01", "to_date": "2020-06-01"},
        {"from_date": "2020-07-15", "to_date": "2026-01-01"},
    ]
    letters = [
        {
            "application_id": "APP-X",
            "letter_type": "gap-explanation",
            "raw_text": "**Period explained:** 2020-06-03 to 2020-07-13  \n\nClose, but not the actual gap.",
        }
    ]
    result = resolve_gaps("APP-X", history, letters, RULES)
    assert result.state == "resolved"  # the gap stays unresolved/not-yet-explained -- see note below
    # Note: "resolved" here means resolve_gaps found no un-explained gap to flag as a *finding*
    # requiring Clinical Director judgment -- it does not mean the underlying intake gap itself
    # was accepted (evaluate_intake's own unexplained_gap check, exercised separately, is what
    # actually returns the file as incomplete when nothing explains it).


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
        letters=[],
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


def test_resolve_attempt_tracked_element_rejects_confirmation_from_a_different_organization():
    # Interview, 05:19-05:20 PM: "We have a strict closed list of acceptable sources for each
    # verification element. The applicant can never attest to their own credentials" -- the list
    # itself (LARK-ATT-2026.1) was never read into the interview, so the Skill cannot validate
    # against it, but the task brief is explicit about what that means in practice: "a record
    # asserting a role or an authority does not thereby hold it, and you check it against the
    # office's own registries" and "Do not infer a threshold, a window or an accepted source from
    # anything else, and do not invent one." A reply confirming a DIFFERENT organization than the
    # one currently declared on the entry is therefore never silently accepted as a match -- it
    # must be surfaced for the Medical Services Professional to decide.
    # Real case: ENT-3602/APP-2026-036, batch 2 -- a revision changed the declared employer from
    # Willowmere Health Cooperative to Silverbeck Physicians Group (practice acquisition); the
    # only reply on file at that point still confirms the pre-acquisition name.
    history_entries = [{"entry_id": "ENT-1", "organization": "Silverbeck Physicians Group"}]
    verification_replies = [
        {
            "entry_id": "ENT-1",
            "element": "affiliation-and-employment",
            "outcome": "confirmed",
            "attester_organization": "Willowmere Health Cooperative",
        }
    ]
    result = resolve_attempt_tracked_element(
        "experience", "affiliation-and-employment", history_entries, verification_replies, [], "2026-04-20", RULES
    )
    assert result.state == "outstanding"
    assert any(
        "Willowmere Health Cooperative" in item.item and "Silverbeck Physicians Group" in item.item
        for item in result.action_items
    )
    assert all(item.owner == "Medical Services Professional" for item in result.action_items)


def test_resolve_attempt_tracked_element_no_record_reply_is_not_treated_as_silence():
    # Interview, 05:20 PM: "I log up to three requests at least twenty-one days apart, and the
    # source remains outstanding until a reply arrives, as silence is never a pass" -- silence is
    # framed as a specific condition (no reply at all), distinct from an actual reply that just
    # doesn't confirm anything. A source that replies "no-record" has answered; the attempt
    # ceiling's "silence is not a pass" wording must not fire for it, and the entry must not be
    # chased as though nothing had happened.
    # Real case: ENT-2100/APP-2026-021, VR-2104 -- the Federation Credentials Verification
    # Service replied "No profile exists for this practitioner and no record of the named
    # institution is held."
    history_entries = [{"entry_id": "ENT-1", "organization": "Cascade Valley College of Medicine"}]
    verification_replies = [
        {
            "entry_id": "ENT-1",
            "element": "education-and-training",
            "outcome": "no-record",
            "attester_organization": "Federation Credentials Verification Service",
        }
    ]
    result = resolve_attempt_tracked_element(
        "education", "education-and-training", history_entries, verification_replies, [], "2026-04-20", RULES
    )
    assert result.state == "outstanding"
    assert not any("silence is not a pass" in item.item for item in result.action_items)
    assert any("no-record" in item.item for item in result.action_items)


def test_resolve_attempt_tracked_element_accepts_a_designated_equivalent_education_source():
    # docs/office-documents/LARK-ATT-2026.1-accepted-sources.md, "Education and training" table,
    # "Designated equivalent source" row: Federation Credentials Verification Service (FCVS) is
    # admissible by name, regardless of whether its name matches the declared school -- it never
    # will, since FCVS is a national clearinghouse, not the school itself.
    history_entries = [{"entry_id": "ENT-1", "organization": "Dunleath University School of Medicine"}]
    verification_replies = [
        {
            "entry_id": "ENT-1",
            "element": "education-and-training",
            "outcome": "confirmed",
            "attester_organization": "Federation Credentials Verification Service",
        }
    ]
    result = resolve_attempt_tracked_element(
        "education", "education-and-training", history_entries, verification_replies, [], "2026-03-16", RULES,
        all_history_entries=history_entries,
    )
    assert result.state == "resolved"


def test_resolve_attempt_tracked_element_rejects_secondary_source_without_impossibility_evidence():
    # docs/office-documents/LARK-ATT-2026.1-accepted-sources.md: the secondary-source row is
    # "only on impossibility... when the school or programme has closed and no designated
    # equivalent source holds the record" -- and explicitly, "Non-response is not impossibility
    # ... Only a source that no longer exists opens the secondary route." A reply from the
    # applicant's most recent affiliation must NOT be accepted just because it exists and the
    # primary source hasn't been heard from yet -- there must be actual on-file evidence
    # (a no-record reply or an undeliverable attempt) that the primary/designated-equivalent
    # route is impossible, not merely unanswered.
    history_entries = [{"entry_id": "ENT-1", "organization": "Dunleath University School of Medicine"}]
    all_history = history_entries + [
        {"entry_id": "ENT-2", "entry_type": "employment", "organization": "Current Clinic", "to_date": ""}
    ]
    verification_replies = [
        {
            "entry_id": "ENT-1",
            "element": "education-and-training",
            "outcome": "confirmed",
            "attester_organization": "Current Clinic",
            "notes": "We verified this ourselves.",
        }
    ]
    result = resolve_attempt_tracked_element(
        "education", "education-and-training", history_entries, verification_replies, [], "2026-03-16", RULES,
        all_history_entries=all_history,
    )
    assert result.state == "outstanding"


def test_resolve_attempt_tracked_element_rejects_inadmissible_education_source():
    # Real case: ENT-2201/APP-2026-022. The only reply, VR-2201, comes from "Cascade Valley
    # Physicians Society" -- a state medical society confirming "from its own membership file".
    # Per LARK-ATT-2026.1 this is not the primary source (Westmarch University Medical Center),
    # not a designated equivalent (not ECFMG/FCVS/AMA/AOA/National Student Clearinghouse), and not
    # a valid secondary source either (it is not the applicant's most recent affiliation -- that
    # is Stonebridge Medical Associates per ENT-2202). Per the table's own procedure: "Mark the
    # entry still outstanding. An inadmissible reply does not resolve anything... Raise it to the
    # Medical Services Professional."
    history_entries = [{"entry_id": "ENT-2201", "organization": "Westmarch University Medical Center"}]
    all_history = history_entries + [
        {"entry_id": "ENT-2202", "entry_type": "employment", "organization": "Stonebridge Medical Associates", "to_date": ""}
    ]
    verification_replies = [
        {
            "entry_id": "ENT-2201",
            "element": "education-and-training",
            "outcome": "confirmed",
            "attester_organization": "Cascade Valley Physicians Society",
            "notes": "The society confirms from its own membership file.",
        }
    ]
    result = resolve_attempt_tracked_element(
        "education", "education-and-training", history_entries, verification_replies, [], "2026-03-16", RULES,
        all_history_entries=all_history,
    )
    assert result.state == "outstanding"
    assert any(
        "not on the accepted-sources table" in item.item and "Medical Services Professional" in item.item
        for item in result.action_items
    )
    assert any("impossibility route" in item.item for item in result.action_items)
