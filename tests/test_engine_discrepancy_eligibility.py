from __future__ import annotations

from scripts.engine import detect_credential_discrepancies, detect_discrepancies, detect_eligibility_mismatch


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


def test_detect_credential_discrepancies_finds_licence_issue_date_mismatch():
    # Interview, 02:23 PM: "I compare the information declared on the application with... all
    # completed verifications. Where any discrepancy arises among these sources... I write to the
    # applicant naming both values." detect_discrepancies (above) only ever covered
    # declared_history; declared_credentials were never compared against licence-lookup-*.csv /
    # certification-replies.csv at all. No real case in office-exports/ has an issue_date
    # mismatch (checked across all 87 declared-credentials rows with a matching lookup row, all
    # three batches) -- this is synthetic, derived directly from the interview's general
    # reconciliation rule, not from an observed failure.
    credentials = [{"declaration_id": "DEC-1", "credential_class": "licence", "number_declared": "MD1", "declared_issue_date": "2011-01-01"}]
    licence_lookup_wa = [{"credentialnumber": "MD1", "firstissuedate": "2013-06-30"}]
    discrepancies = detect_credential_discrepancies(credentials, licence_lookup_wa, [], [])
    assert len(discrepancies) == 1
    assert discrepancies[0]["declaration_id"] == "DEC-1"
    assert discrepancies[0]["credential_class"] == "licence"
    assert discrepancies[0]["field"] == "declared_issue_date"
    assert discrepancies[0]["declared"] == "2011-01-01"
    assert discrepancies[0]["verified"] == "2013-06-30"


def test_detect_credential_discrepancies_finds_certification_issue_date_mismatch():
    credentials = [
        {"declaration_id": "DEC-2", "credential_class": "certification", "declared_issue_date": "2010-01-01"}
    ]
    certification_replies = [{"declaration_id": "DEC-2", "initial_certification_date": "2012-01-01"}]
    discrepancies = detect_credential_discrepancies(credentials, [], [], certification_replies)
    assert len(discrepancies) == 1
    assert discrepancies[0]["credential_class"] == "certification"
    assert discrepancies[0]["field"] == "declared_issue_date"


def test_detect_credential_discrepancies_empty_when_dates_match():
    credentials = [{"declaration_id": "DEC-1", "credential_class": "licence", "number_declared": "MD1", "declared_issue_date": "2011-06-27"}]
    licence_lookup_wa = [{"credentialnumber": "MD1", "firstissuedate": "2011-06-27"}]
    assert detect_credential_discrepancies(credentials, licence_lookup_wa, [], []) == []


def test_detect_credential_discrepancies_ignores_expiry_date_drift_from_a_renewal():
    # Real case: APP-2026-040's WA licence (MD60096330, declared_expiry_date 2026-04-10 at
    # intake). It renewed between batch 2 and batch 3 -- licence-lookup-wa.csv's expirationdate
    # moved to 2028-04-30 while firstissuedate stayed fixed at 2011-06-27. A naive
    # declared-vs-verified comparison on expiry_date would have flagged this as a discrepancy
    # needing the applicant's written explanation, when nothing was ever misdeclared -- the
    # licence simply renewed after the application was filed. Only issue_date (stable, never
    # moves) is compared; expiry_date is deliberately excluded.
    credentials = [
        {
            "declaration_id": "DEC-4000",
            "credential_class": "licence",
            "number_declared": "MD60096330",
            "declared_issue_date": "2011-06-27",
            "declared_expiry_date": "2026-04-10",
        }
    ]
    licence_lookup_wa = [
        {
            "credentialnumber": "MD60096330",
            "firstissuedate": "2011-06-27",
            "expirationdate": "2028-04-30",
        }
    ]
    assert detect_credential_discrepancies(credentials, licence_lookup_wa, [], []) == []


def test_detect_credential_discrepancies_ignores_status_vocabulary_differences():
    # Real-data regression guard: the application form and the board's own reply use different
    # vocabularies for the same fact -- the application declares "Board certified", the board
    # replies "Active" -- confirmed across every one of the office's three real batches (38 of 40
    # certification-replies.csv rows use exactly this pair). Comparing declared_status against
    # the verified status text directly, the obvious-looking next step, would flag nearly every
    # certification in the real caseload as a false discrepancy. This must never be compared.
    credentials = [
        {
            "declaration_id": "DEC-1",
            "credential_class": "certification",
            "declared_status": "Board certified",
            "declared_expiry_date": "2030-12-31",
        }
    ]
    certification_replies = [
        {"declaration_id": "DEC-1", "certification_status": "Active", "expiry_date": "2030-12-31"}
    ]
    assert detect_credential_discrepancies(credentials, [], [], certification_replies) == []


# docs/office-documents/LARK-PRIV-2026.1-privilege-criteria.md, "How the office applies the
# table" (rules 1-6). Fixtures below model the real data shapes: declared_credentials joins to
# certification_replies by declaration_id; a residency's declared_history row joins to
# verification_replies by entry_id+element to count as "verified training."


def _fm_residency_history():
    history = [{"entry_id": "ENT-RES", "entry_type": "residency", "role": "Family Medicine Residency", "from_date": "2010-07-01", "to_date": "2013-06-30"}]
    replies = [{"entry_id": "ENT-RES", "element": "education-and-training", "outcome": "confirmed"}]
    return history, replies


def test_eligibility_mismatch_true_when_nothing_supports_requested_privilege():
    # Real-shaped case: APP-2026-029 (orthopaedic surgery requested, nothing on file supports
    # it). Rule 1: a supported group needs a verified certification from the group's named
    # boards, in the specialty named -- family medicine training/certification doesn't satisfy
    # orthopaedic surgery's criteria row at all.
    priv_requests = [{"privilege_code": "PRIV-ORTHO"}]
    history, verification_replies = _fm_residency_history()
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {"declaration_id": "DEC-1", "board_code": "ABFM", "certificate_specialty": "Family Medicine", "certification_status": "Active"}
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is True


def test_eligibility_mismatch_false_when_board_and_training_support_privilege():
    priv_requests = [{"privilege_code": "PRIV-FM"}]
    history, verification_replies = _fm_residency_history()
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {"declaration_id": "DEC-1", "board_code": "ABFM", "certificate_specialty": "Family Medicine", "certification_status": "Active"}
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is False


def test_eligibility_mismatch_true_when_training_below_minimum_months():
    # Rule 1's training requirement is a real minimum (36 months for PRIV-FM), not merely "some
    # training in the specialty" -- a verified residency of only 12 months does not meet it.
    priv_requests = [{"privilege_code": "PRIV-FM"}]
    history = [{"entry_id": "ENT-RES", "entry_type": "residency", "role": "Family Medicine Residency", "from_date": "2010-07-01", "to_date": "2011-06-30"}]
    verification_replies = [{"entry_id": "ENT-RES", "element": "education-and-training", "outcome": "confirmed"}]
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {"declaration_id": "DEC-1", "board_code": "ABFM", "certificate_specialty": "Family Medicine", "certification_status": "Active"}
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is True


def test_eligibility_mismatch_true_when_certification_inactive():
    # Rule 3: "An inactive or expired certification does not support a privilege group." The
    # credential is still verified and recorded (resolve_certification's own job), but it
    # supports nothing here, even with otherwise-sufficient training.
    priv_requests = [{"privilege_code": "PRIV-FM"}]
    history, verification_replies = _fm_residency_history()
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {"declaration_id": "DEC-1", "board_code": "ABFM", "certificate_specialty": "Family Medicine", "certification_status": "Inactive"}
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is True


def test_eligibility_mismatch_false_via_board_eligible_exception_for_allowed_group():
    # Real case: CR-01000/APP-2026-010 -- "Candidate in good standing; board eligible through
    # 2027-06-30," certification_status "Not certified", requesting PRIV-PED (one of the four
    # groups rule 4 allows the board-eligible exception for).
    priv_requests = [{"privilege_code": "PRIV-PED"}]
    history = [{"entry_id": "ENT-RES", "entry_type": "residency", "role": "Pediatrics Residency", "from_date": "2019-07-01", "to_date": "2022-06-30"}]
    verification_replies = [{"entry_id": "ENT-RES", "element": "education-and-training", "outcome": "confirmed"}]
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {
            "declaration_id": "DEC-1",
            "board_code": "ABP",
            "certificate_specialty": "Pediatrics",
            "certification_status": "Not certified",
            "notes": "Candidate in good standing; board eligible through 2027-06-30.",
        }
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is False


def test_eligibility_mismatch_true_via_board_eligible_exception_for_disallowed_group():
    # Rule 4: "Board eligible is not accepted for... PRIV-GS..." -- the same board-eligible
    # notes that support PRIV-PED must not support a group outside the four allowed.
    priv_requests = [{"privilege_code": "PRIV-GS"}]
    history = [{"entry_id": "ENT-RES", "entry_type": "residency", "role": "General Surgery Residency", "from_date": "2010-07-01", "to_date": "2015-06-30"}]
    verification_replies = [{"entry_id": "ENT-RES", "element": "education-and-training", "outcome": "confirmed"}]
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {
            "declaration_id": "DEC-1",
            "board_code": "ABS",
            "certificate_specialty": "Surgery",
            "certification_status": "Not certified",
            "notes": "Candidate in good standing; board eligible through 2030-06-30.",
        }
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is True


def test_eligibility_mismatch_true_for_priv_card_without_a_fellowship():
    # Real case: APP-2026-026 requests PRIV-CARD with an active Internal Medicine certification
    # and an Internal Medicine residency, but no fellowship at all -- rule 5 requires both the
    # cardiovascular disease fellowship and the antecedent internal medicine residency; the
    # residency alone, however well-verified, does not support it.
    priv_requests = [{"privilege_code": "PRIV-CARD"}]
    history = [
        {"entry_id": "ENT-RES", "entry_type": "residency", "role": "Internal Medicine Residency", "from_date": "2007-07-01", "to_date": "2010-06-30"},
    ]
    verification_replies = [{"entry_id": "ENT-RES", "element": "education-and-training", "outcome": "confirmed"}]
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {"declaration_id": "DEC-1", "board_code": "ABIM", "certificate_specialty": "Cardiovascular Disease", "certification_status": "Active"}
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is True


def test_eligibility_mismatch_false_for_priv_card_with_fellowship_and_antecedent_residency():
    # Positive mirror of the real case above -- no real application in office-exports/ has a
    # fellowship entry at all (confirmed across all three batches), so this is synthetic, derived
    # directly from rule 5.
    priv_requests = [{"privilege_code": "PRIV-CARD"}]
    history = [
        {"entry_id": "ENT-RES", "entry_type": "residency", "role": "Internal Medicine Residency", "from_date": "2007-07-01", "to_date": "2010-06-30"},
        {"entry_id": "ENT-FEL", "entry_type": "fellowship", "role": "Cardiovascular Disease Fellowship", "from_date": "2010-07-01", "to_date": "2013-06-30"},
    ]
    verification_replies = [
        {"entry_id": "ENT-RES", "element": "education-and-training", "outcome": "confirmed"},
        {"entry_id": "ENT-FEL", "element": "education-and-training", "outcome": "confirmed"},
    ]
    credentials = [{"credential_class": "certification", "declaration_id": "DEC-1"}]
    certification_replies = [
        {"declaration_id": "DEC-1", "board_code": "ABIM", "certificate_specialty": "Cardiovascular Disease", "certification_status": "Active"}
    ]
    assert detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, "2026-03-16", verification_replies) is False


def test_eligibility_mismatch_false_with_no_privilege_requests():
    assert detect_eligibility_mismatch([], [], [], [], "2026-03-16", []) is False


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


def test_detect_ppq_verification_mismatch_real_case_app_2026_015():
    # docs/office-documents/LARK-APP-2026.1-application-form.md, Section I: "If a verification
    # the office receives shows that a Yes was owed and a No was given, the office will contact
    # you to confirm the answer before the file goes any further." Real case: APP-2026-015
    # declared PPQ-1 "No" (application-disclosures.csv); the WA board's own lookup
    # (licence-lookup-wa.csv) shows actiontaken "Yes" for credential MD60069441 (a stipulated
    # agreement). The office's own letter,
    # office-exports/batch-02/letters/2026-04-02_confirm-disclosure_APP-2026-015.md, is this
    # exact procedure: "Your application answers No... please confirm in writing whether that
    # answer is correct, or submit a revision."
    from scripts.engine import detect_ppq_verification_mismatch

    disclosures = [{"question_code": "PPQ-1", "answer": "No", "applicant_comment": ""}]
    credentials = [{"credential_class": "licence", "number_declared": "MD60069441"}]
    licence_lookup_wa = [{"credentialnumber": "MD60069441", "actiontaken": "Yes"}]
    mismatches = detect_ppq_verification_mismatch(disclosures, credentials, licence_lookup_wa, [])
    assert len(mismatches) == 1
    assert mismatches[0]["question_code"] == "PPQ-1"
    assert mismatches[0]["declared"] == "No"
    assert mismatches[0]["verified"] == "Yes"


def test_detect_ppq_verification_mismatch_empty_when_declared_yes():
    # A declared "Yes" already gets its own high-risk-finding routing via detect_ppq_findings --
    # this check is specifically for an owed Yes that was answered No.
    from scripts.engine import detect_ppq_verification_mismatch

    disclosures = [{"question_code": "PPQ-1", "answer": "Yes", "applicant_comment": "Explained."}]
    credentials = [{"credential_class": "licence", "number_declared": "MD1"}]
    licence_lookup_wa = [{"credentialnumber": "MD1", "actiontaken": "Yes"}]
    assert detect_ppq_verification_mismatch(disclosures, credentials, licence_lookup_wa, []) == []


def test_detect_ppq_verification_mismatch_empty_when_no_board_action():
    from scripts.engine import detect_ppq_verification_mismatch

    disclosures = [{"question_code": "PPQ-1", "answer": "No", "applicant_comment": ""}]
    credentials = [{"credential_class": "licence", "number_declared": "MD1"}]
    licence_lookup_wa = [{"credentialnumber": "MD1", "actiontaken": "No"}]
    assert detect_ppq_verification_mismatch(disclosures, credentials, licence_lookup_wa, []) == []


def test_detect_ppq_verification_mismatch_stops_once_a_disposition_covers_the_file():
    # Real bug, found by the project owner tracing APP-2026-015's full letter trail: the declared
    # PPQ-1 answer in application-disclosures.csv never changes (office-note-2026-03-16-export-
    # format.md: a correction arrives as correspondence, not a new application revision, so the
    # declared field stays frozen at "No" forever) -- so a check that only compares
    # declared-vs-verified has no way to ever stop firing, even once the Clinical Director has
    # read the applicant's confirmation and acted on it (real case:
    # office-exports/batch-03/dispositions/2026-05-06_disposition_APP-2026-015.md: "I have read...
    # the applicant's written confirmation of 2026-04-20... Present the file to the Executive
    # Committee"). Once any disposition exists for the application, the Clinical Director has
    # reviewed the file's open items and the Skill defers to that human record, the same
    # "consume the human record once it exists" precedent the rest of this codebase already
    # follows (apply_dispositions clearing a flagged element on a disposition, admit_decision/
    # admit_disposition only ever validating -- never second-guessing -- an admitted human record).
    from scripts.engine import detect_ppq_verification_mismatch

    disclosures = [{"question_code": "PPQ-1", "answer": "No", "applicant_comment": ""}]
    credentials = [{"credential_class": "licence", "number_declared": "MD60069441"}]
    licence_lookup_wa = [{"credentialnumber": "MD60069441", "actiontaken": "Yes"}]
    dispositions = [{"filename": "d.md", "date": "2026-05-06", "raw_text": "Present the file to the Executive Committee."}]
    assert detect_ppq_verification_mismatch(disclosures, credentials, licence_lookup_wa, [], dispositions=dispositions) == []


def test_detect_ppq_verification_mismatch_stops_once_the_applicant_replies_in_writing():
    # Short of a disposition: real case, batch 3's own correspondence.csv (LTR-0057) --
    # office-exports/batch-03/letters/2026-04-20_confirm-disclosure-reply_APP-2026-015.md is the
    # applicant's written confirmation, received before the Clinical Director's disposition
    # (2026-05-06) was recorded. The nag must stop once the applicant has already answered the
    # office's own request, not wait for the disposition too.
    from scripts.engine import detect_ppq_verification_mismatch

    disclosures = [{"question_code": "PPQ-1", "answer": "No", "applicant_comment": ""}]
    credentials = [{"credential_class": "licence", "number_declared": "MD60069441"}]
    licence_lookup_wa = [{"credentialnumber": "MD60069441", "actiontaken": "Yes"}]
    letters = [
        {
            "application_id": "APP-2026-015",
            "letter_type": "confirm-disclosure-reply",
            "raw_text": "Confirmation of my answer to professional practice question PPQ-1",
        }
    ]
    assert (
        detect_ppq_verification_mismatch(
            disclosures, credentials, licence_lookup_wa, [], dispositions=[], reply_letters=letters
        )
        == []
    )


def test_detect_ppq_verification_mismatch_still_fires_before_either_signal_exists():
    # Real case, batch 1 and batch 2: before the Clinical Director's disposition and before the
    # applicant's written reply, the item must still fire -- this is the actual, still-open gap
    # the office's own confirm-disclosure letter exists to close.
    from scripts.engine import detect_ppq_verification_mismatch

    disclosures = [{"question_code": "PPQ-1", "answer": "No", "applicant_comment": ""}]
    credentials = [{"credential_class": "licence", "number_declared": "MD60069441"}]
    licence_lookup_wa = [{"credentialnumber": "MD60069441", "actiontaken": "Yes"}]
    mismatches = detect_ppq_verification_mismatch(
        disclosures, credentials, licence_lookup_wa, [], dispositions=[], reply_letters=[]
    )
    assert len(mismatches) == 1
