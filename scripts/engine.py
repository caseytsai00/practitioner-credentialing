from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from scripts.model import (
    ELEMENT_NAMES,
    ActionItem,
    Activation,
    ApplicationRecord,
    Decision,
    MonitoredCondition,
)
from scripts.parsers import filter_rows
from scripts.state import get_application_entry


def _parse_date(value: str) -> Optional[datetime.date]:
    if not value:
        return None
    year, month, day = (int(part) for part in value.split("-"))
    return datetime.date(year, month, day)


def _add_days(date_: datetime.date, delta: int) -> datetime.date:
    return date_ + datetime.timedelta(days=delta)


@dataclass
class IntakeResult:
    status: str
    missing_items: List[str] = field(default_factory=list)
    action_items: List[ActionItem] = field(default_factory=list)
    clock_due: Optional[str] = None


def missing_intake_items(app_row, disclosures, history, credentials, priv_requests, referees, rules) -> List[str]:
    missing: List[str] = []
    if not app_row.get("received_date"):
        missing.append("the application, signed and dated")
    if not app_row.get("release_signed_date"):
        missing.append("the Larkhollow Authorization and Release, signed and dated")
    if not priv_requests:
        missing.append("a privilege request naming at least one group from the current criteria")
    else:
        current_criteria_version = rules["intake.current_criteria_version"]
        # A blank/absent criteria_version_cited isn't evidence of a stale citation -- only an
        # explicit, populated, non-matching one is (same leniency as this function's other
        # data-derived checks below, which treat missing data as satisfied rather than inventing
        # a problem from it).
        cited_versions = [r.get("criteria_version_cited") for r in priv_requests if r.get("criteria_version_cited")]
        if cited_versions and current_criteria_version not in cited_versions:
            missing.append(
                "a privilege request naming a group from the current criteria (on file cites {}, current is {})".format(
                    ", ".join(sorted(set(cited_versions))), current_criteria_version
                )
            )
    if not app_row.get("cv_received_date"):
        missing.append("a current curriculum vitae")
    for disclosure in disclosures:
        if disclosure.get("answer") == "Yes" and not disclosure.get("applicant_comment"):
            missing.append(
                "a written explanation for {}".format(disclosure.get("question_code", "a yes answer"))
            )
    if not credentials:
        missing.append("every licence and certification the applicant holds declared")
    required_referees = rules["references.required_count"]
    if len(referees) < required_referees:
        # office-note-2026-03-16-export-format.md: "The export carries no address column for
        # peer referees... a run assesses condition 7 on the named referees alone and records the
        # address check as not assessable from the export -- neither met nor failed." The prior
        # wording here ("...with a working address each") falsely implied the address half was
        # being checked; it never was, since there's no address field anywhere in the export.
        missing.append("at least {} peer referees named".format(required_referees))
    for entry in history:
        if entry.get("entry_type") in ("employment", "teaching") and not (
            entry.get("contact_name") or entry.get("contact_email")
        ):
            missing.append(
                "a verification contact for {}".format(entry.get("organization", "a declared affiliation"))
            )
    return missing


_PERIOD_EXPLAINED_RE = re.compile(r"\*\*Period explained:\*\*\s*(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})")


def _gap_is_explained(application_id: str, gap_start: datetime.date, gap_end: datetime.date, letters) -> bool:
    # LARK-APP-2026.1, Section F: "Begin the explanation with the line Period explained: <from
    # date> to <to date>... the office matches your explanation to the period by those two dates
    # and by nothing else." Previously matched against correspondence.csv's own `subject` column
    # (an office-authored index -- the office's own export note warns it "does not tell you what
    # they say"), via loose substring containment rather than the letter's own stated dates
    # exactly. Confirmed across all 4 real gap-explanation letters: every one carries a
    # **Period explained:** field in exactly this format.
    start_label = gap_start.isoformat()
    end_label = gap_end.isoformat()
    for letter in letters:
        if letter.get("application_id") != application_id or letter.get("letter_type") != "gap-explanation":
            continue
        match = _PERIOD_EXPLAINED_RE.search(letter.get("raw_text", ""))
        if match and match.group(1) == start_label and match.group(2) == end_label:
            return True
    return False


def unexplained_gap(application_id: str, history, letters, rules) -> Optional[Dict[str, object]]:
    threshold = rules["intake.unexplained_gap_days"]
    entries = sorted((e for e in history if e.get("from_date")), key=lambda e: e["from_date"])
    for earlier, later in zip(entries, entries[1:]):
        gap_start_edge = _parse_date(earlier.get("to_date") or "")
        gap_end_edge = _parse_date(later["from_date"])
        if gap_start_edge is None or gap_end_edge is None:
            continue
        gap_days = (gap_end_edge - gap_start_edge).days - 1
        if gap_days < threshold:
            continue
        gap_start = _add_days(gap_start_edge, 1)
        gap_end = _add_days(gap_end_edge, -1)
        if not _gap_is_explained(application_id, gap_start, gap_end, letters):
            return {"from": gap_start.isoformat(), "to": gap_end.isoformat(), "days": gap_days}
    return None


def _find_missing_items_letter_date(application_id: str, correspondence) -> Optional[str]:
    dates = [
        row["date"]
        for row in correspondence
        if row.get("application_id") == application_id
        and row.get("direction") == "outbound"
        and "missing" in row.get("subject", "").lower()
    ]
    return min(dates) if dates else None


def evaluate_intake(
    *,
    application_id: str,
    app_row: dict,
    disclosures,
    history,
    credentials,
    priv_requests,
    referees,
    correspondence,
    letters,
    as_of: str,
    rules,
) -> IntakeResult:
    gap = unexplained_gap(application_id, history, letters, rules)
    if gap is not None:
        return IntakeResult(
            status="returned-incomplete",
            missing_items=[
                "an unexplained period {} to {} ({} days)".format(gap["from"], gap["to"], gap["days"])
            ],
            action_items=[
                ActionItem(
                    item="Send return-incomplete letter naming the unexplained period {} to {}".format(
                        gap["from"], gap["to"]
                    ),
                    owner="Medical Services Professional",
                )
            ],
        )

    missing = missing_intake_items(app_row, disclosures, history, credentials, priv_requests, referees, rules)
    if not missing:
        return IntakeResult(status="complete")

    clock_start = _find_missing_items_letter_date(application_id, correspondence)
    if clock_start is None:
        return IntakeResult(
            status="intake-incomplete",
            missing_items=missing,
            action_items=[
                ActionItem(
                    item="Send missing-items letter naming: {}".format("; ".join(missing)),
                    owner="Medical Services Professional",
                )
            ],
        )

    clock_days = rules["intake.missing_items_clock_days"]
    due = _add_days(_parse_date(clock_start), clock_days)
    if _parse_date(as_of) > due:
        return IntakeResult(
            status="ineligible-clock-expired",
            missing_items=missing,
            action_items=[
                ActionItem(
                    item="Confirm the file should be treated as ineligible; the 30-day clock expired {}".format(
                        due.isoformat()
                    ),
                    owner="Medical Services Professional",
                )
            ],
        )

    return IntakeResult(
        status="intake-incomplete",
        missing_items=missing,
        clock_due=due.isoformat(),
        action_items=[
            ActionItem(
                item="Awaiting applicant reply to missing-items letter",
                owner="Applicant",
                due=due.isoformat(),
            )
        ],
    )


@dataclass
class ElementResult:
    state: str
    action_items: List[ActionItem] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def resolve_licensure(credentials, licence_lookup_wa, licence_lookup_other, as_of, app_row=None) -> ElementResult:
    licence_credentials = [c for c in credentials if c.get("credential_class") == "licence"]
    if not licence_credentials:
        return ElementResult(
            state="outstanding",
            action_items=[ActionItem(item="No licence declared to verify", owner="Medical Services Professional")],
        )
    as_of_date = _parse_date(as_of)
    app_row = app_row or {}
    for cred in licence_credentials:
        number = cred.get("number_declared")
        confirmed_absent = False
        if cred.get("jurisdiction_or_board") == "WA" and app_row:
            # office-note-2026-03-16-export-format.md: "The Washington board export carries no
            # practitioner identifier. It never has. I join it to an application on lastname,
            # firstname, middlename and birthyear... An applicant with no row in that file holds
            # no Washington credential. The absence is the answer, not a data problem." The
            # declared licence number is never the real join key for this file -- matching by it
            # (as this did previously) happened to agree with the name+birthyear join on every
            # row in all three batches, but isn't how the office actually establishes absence.
            match = next(
                (
                    row
                    for row in licence_lookup_wa
                    if row.get("lastname") == app_row.get("last_name")
                    and row.get("firstname") == app_row.get("first_name")
                    and row.get("middlename") == (app_row.get("middle_name") or "")
                    and row.get("birthyear") == app_row.get("birth_year")
                ),
                None,
            )
            confirmed_absent = match is None
        else:
            match = next(
                (
                    row
                    for row in licence_lookup_wa + licence_lookup_other
                    if row.get("credentialnumber") == number or row.get("licence_number") == number
                ),
                None,
            )
        if match is None:
            item = (
                "No Washington board record exists for this applicant (checked by name and birth year, "
                "per the office's own join) -- the declared licence {} is confirmed absent, not unresolved "
                "data".format(number)
                if confirmed_absent
                else "No current board record found for licence {}".format(number)
            )
            return ElementResult(
                state="outstanding",
                action_items=[ActionItem(item=item, owner="Medical Services Professional")],
            )
        action_taken = match.get("actiontaken") or match.get("disciplinary_action") or "No"
        if action_taken not in ("No", "None reported"):
            return ElementResult(
                state="finding",
                action_items=[
                    ActionItem(
                        item="Board action on licence {} needs Clinical Director review".format(number),
                        owner="Clinical Director",
                    )
                ],
            )
        status = (match.get("status") or "").upper()
        expiry = _parse_date(match.get("expirationdate") or match.get("expiry_date") or "")
        if status != "ACTIVE" or (expiry is not None and expiry < as_of_date):
            return ElementResult(
                state="outstanding",
                action_items=[
                    ActionItem(
                        item="Licence {} is not active and current as of {}".format(number, as_of),
                        owner="Medical Services Professional",
                    )
                ],
            )
    return ElementResult(state="resolved")


def _organizations_match(declared_organization, attester_organization):
    declared = (declared_organization or "").strip().lower()
    attester = (attester_organization or "").strip().lower()
    if not declared or not attester:
        return True
    return declared == attester


def _name_in_list(text, names):
    normalized = (text or "").strip().lower()
    return any(name in normalized for name in names)


# docs/office-documents/LARK-ATT-2026.1-accepted-sources.md, "Education and training" table,
# "Designated equivalent source" row. Matched by substring, case-insensitive, since real
# attester_organization values vary in phrasing (e.g. "Federation Credentials Verification
# Service" vs "FCVS — Federation Credentials Verification Service" elsewhere in the office's own
# documents) but will never equal the declared school's own name -- that's the point of this list.
_EDUCATION_DESIGNATED_EQUIVALENT_SOURCES = (
    "educational commission for foreign medical graduates",
    "ecfmg",
    "federation credentials verification service",
    "fcvs",
    "american medical association physician profile",
    "american osteopathic association physician profile",
    "national student clearinghouse",
)


def _most_recent_affiliation_organization(all_history_entries):
    affiliations = [h for h in (all_history_entries or []) if h.get("entry_type") in ("employment", "teaching")]
    if not affiliations:
        return None

    def _sort_key(entry):
        # an open-ended entry (no to_date -- still current) is the most recent; otherwise the
        # latest to_date wins.
        return (1, "") if not entry.get("to_date") else (0, entry["to_date"])

    return max(affiliations, key=_sort_key).get("organization")


def _has_impossibility_evidence_on_file(entry_id, element_label, entry_replies, verification_attempts):
    # docs/office-documents/LARK-ATT-2026.1-accepted-sources.md: "Non-response is not
    # impossibility... Only a source that no longer exists opens the secondary route." A
    # no-record reply from a designated-equivalent source, or an undeliverable attempt against
    # the primary source, is on-file evidence the route is actually impossible -- an unanswered
    # request is not.
    if any(r.get("outcome") == "no-record" for r in entry_replies):
        return True
    return any(
        a.get("subject_ref") == entry_id and a.get("element") == element_label and a.get("outcome") == "undeliverable"
        for a in (verification_attempts or [])
    )


def _education_source_admission(
    declared_organization, reply, entry_id, all_history_entries, entry_replies, verification_attempts
):
    """Classifies one reply's source against LARK-ATT-2026.1's education-and-training table.
    Returns "primary", "designated_equivalent", "secondary", or "inadmissible"."""
    attester = reply.get("attester_organization")
    if _organizations_match(declared_organization, attester):
        return "primary"
    if _name_in_list(attester, _EDUCATION_DESIGNATED_EQUIVALENT_SOURCES):
        return "designated_equivalent"
    most_recent = _most_recent_affiliation_organization(all_history_entries)
    if (
        most_recent
        and _organizations_match(most_recent, attester)
        and (reply.get("notes") or "").strip()
        and _has_impossibility_evidence_on_file(entry_id, "education-and-training", entry_replies, verification_attempts)
    ):
        return "secondary"
    return "inadmissible"


def resolve_attempt_tracked_element(
    element_name,
    element_label,
    history_entries,
    verification_replies,
    verification_attempts,
    as_of,
    rules,
    all_history_entries=None,
) -> ElementResult:
    if not history_entries:
        return ElementResult(
            state="outstanding",
            action_items=[
                ActionItem(
                    item="No {} entries declared to verify".format(element_name),
                    owner="Medical Services Professional",
                )
            ],
        )
    max_attempts = rules["verification.attempt_max_count"]
    min_spacing = rules["verification.attempt_min_spacing_days"]
    is_education = element_label == "education-and-training"
    action_items = []
    all_confirmed = True
    for entry in history_entries:
        entry_id = entry["entry_id"]
        declared_organization = entry.get("organization")
        entry_replies = [
            r for r in verification_replies if r.get("entry_id") == entry_id and r.get("element") == element_label
        ]

        def _admission(reply):
            if is_education:
                return _education_source_admission(
                    declared_organization, reply, entry_id, all_history_entries, entry_replies, verification_attempts
                )
            # affiliation-and-employment: per
            # docs/office-documents/LARK-ATT-2026.1-accepted-sources.md's primary-source row (the
            # employer's own medical staff office/HR department), the entity being verified *is*
            # the employer, so matching the currently declared employer's name is itself the
            # admissibility test for this element -- unlike education/licensure/certification,
            # where the designated-equivalent sources are a closed list of third parties that will
            # never share the primary source's name. No batch's data contains an instance of this
            # element's designated-equivalent (a retained CVO) or secondary-source (employer
            # dissolved, no successor) rows, so neither is coded here -- there's nothing to
            # validate either check against yet.
            return "primary" if _organizations_match(declared_organization, reply.get("attester_organization")) else "inadmissible"

        # "confirmed-with-discrepancy" means the source DID reply -- the discrepancy itself is
        # handled separately (detect_discrepancies / the applicant resolving it in writing or by
        # amendment), so treating only a bare "confirmed" as a reply leaves an otherwise-settled
        # entry permanently "outstanding" even after the applicant corrects the value (real case:
        # VR-3002/APP-2026-030).
        confirmed = any(
            r.get("outcome") in ("confirmed", "confirmed-with-discrepancy") and _admission(r) != "inadmissible"
            for r in entry_replies
        )
        if confirmed:
            continue
        all_confirmed = False
        source_label = declared_organization or entry_id
        if entry_replies:
            # At least one source replied, but nothing on file settles the record. Silence
            # framing (handled below) is for when no reply exists at all -- this is different,
            # and which kind of different matters: a reply from a source not on
            # LARK-ATT-2026.1's table at all must follow that document's own four-step procedure,
            # never a generic message, per the Medical Services Professional's explicit
            # correction (2026-10-04) to an earlier, broader "does not settle the record" wording
            # that didn't distinguish the two.
            admissions = [(_admission(r), r) for r in entry_replies]
            inadmissible = [(a, r) for a, r in admissions if a == "inadmissible"]
            if inadmissible:
                descriptions = [
                    "{} is not on the accepted-sources table".format(r.get("attester_organization") or "an unnamed source")
                    for _, r in inadmissible
                ]
                action_items.append(
                    ActionItem(
                        item=(
                            "{} reply for {}: {}; recorded as received, the entry stays outstanding, "
                            "keep requesting from an accepted source, and raise to the Medical Services "
                            "Professional to decide whether an impossibility route applies".format(
                                element_name, source_label, "; ".join(descriptions)
                            )
                        ),
                        owner="Medical Services Professional",
                    )
                )
            else:
                # Every reply came from an admissible source but none confirmed this entry (real
                # case: ENT-2100/APP-2026-021 before its secondary reply arrived, when only
                # FCVS's "no-record" was on file) -- the source itself is fine, it just hasn't
                # settled anything, so this isn't a wrong-source problem and shouldn't read as
                # silence either.
                descriptions = []
                for reply in entry_replies:
                    outcome = reply.get("outcome")
                    attester = reply.get("attester_organization") or "an unnamed source"
                    if outcome in ("confirmed", "confirmed-with-discrepancy"):
                        descriptions.append(
                            "{} confirms this, but the declared record names {}".format(attester, source_label)
                        )
                    else:
                        descriptions.append("an accepted source ({}) replied '{}'".format(attester, outcome))
                action_items.append(
                    ActionItem(
                        item="{} reply for {} does not settle the record: {}; Medical Services Professional must decide how to proceed".format(
                            element_name, source_label, "; ".join(descriptions)
                        ),
                        owner="Medical Services Professional",
                    )
                )
            continue
        attempts = sorted(
            (a for a in verification_attempts if a.get("subject_ref") == entry_id and a.get("element") == element_label),
            key=lambda a: a["attempt_date"],
        )
        if len(attempts) >= max_attempts:
            action_items.append(
                ActionItem(
                    item="{} source {} has not replied after {} attempts; silence is not a pass".format(
                        element_name, source_label, max_attempts
                    ),
                    owner="Medical Services Professional",
                )
            )
        else:
            due = None
            if attempts:
                due = _add_days(_parse_date(attempts[-1]["attempt_date"]), min_spacing).isoformat()
            action_items.append(
                ActionItem(
                    item="Chase {} verification with {}".format(element_name, source_label),
                    owner="Medical Services Professional",
                    due=due,
                )
            )
    if all_confirmed:
        return ElementResult(state="resolved")
    return ElementResult(state="outstanding", action_items=action_items)


# docs/office-documents/LARK-ATT-2026.1-accepted-sources.md, "Board certification" table,
# "Designated equivalent source" row. Same substring/case-insensitive matching rationale as
# education's list -- these will never equal the declared issuing board's own name.
_CERTIFICATION_DESIGNATED_EQUIVALENT_SOURCES = (
    "american board of medical specialties",
    "abms",
    "certifacts",
    "american medical association physician profile",
    "american osteopathic association physician profile",
    "american board of physician specialties",
    "abps",
    "american nurses credentialing center",
    "ancc",
    "national commission on certification of physician assistants",
    "nccpa",
)


def resolve_certification(credentials, certification_replies, as_of) -> ElementResult:
    cert_credentials = [c for c in credentials if c.get("credential_class") == "certification"]
    if not cert_credentials:
        return ElementResult(
            state="outstanding",
            action_items=[ActionItem(item="No certification declared to verify", owner="Medical Services Professional")],
        )
    action_items = []
    all_confirmed = True
    for cred in cert_credentials:
        reply = next(
            (r for r in certification_replies if r.get("declaration_id") == cred.get("declaration_id")), None
        )
        if reply is None or not reply.get("received_date"):
            all_confirmed = False
            action_items.append(
                ActionItem(
                    item="Chase certification reply for {}".format(cred.get("issuer", cred.get("declaration_id"))),
                    owner="Medical Services Professional",
                )
            )
            continue
        board_name = reply.get("board_name")
        admissible = _organizations_match(cred.get("issuer"), board_name) or _name_in_list(
            board_name, _CERTIFICATION_DESIGNATED_EQUIVALENT_SOURCES
        )
        if not admissible:
            # Per LARK-ATT-2026.1's "What to do with a reply that is not on this table": record
            # it, keep the entry outstanding (not `finding` -- `finding` is a real, trusted
            # determination for the Clinical Director to judge, and an inadmissible reply isn't
            # evidence the Skill may trust at all), keep requesting from an accepted source, and
            # raise it to the Medical Services Professional. No real case in the office's three
            # batches exercises this (every certification-replies.csv row comes directly from the
            # issuing board itself) -- implemented from the table directly, not from an observed
            # failure.
            all_confirmed = False
            action_items.append(
                ActionItem(
                    item=(
                        "certification reply for {} is from {}, not on the accepted-sources table; "
                        "recorded as received, the entry stays outstanding, keep requesting from an "
                        "accepted source, and raise to the Medical Services Professional to decide "
                        "whether an impossibility route applies".format(
                            cred.get("issuer", cred.get("declaration_id")), board_name or "an unnamed source"
                        )
                    ),
                    owner="Medical Services Professional",
                )
            )
            continue
        status = (reply.get("certification_status") or "").lower()
        if status not in ("active", "board certified"):
            return ElementResult(
                state="finding",
                action_items=[
                    ActionItem(
                        item="Certification for {} shows status '{}'; route to Clinical Director".format(
                            cred.get("issuer", cred.get("declaration_id")), reply.get("certification_status")
                        ),
                        owner="Clinical Director",
                    )
                ],
            )
        # A reply's certification_status reflects what the board said when it replied -- it is
        # never re-fetched, so a certification can go stale while a file waits exactly the way a
        # licence can (interview, opening remarks, 07:13 PM: "a file sits ready for the committee
        # for weeks while a licence expires underneath it"). resolve_licensure already re-checks
        # its expiry on every run; resolve_certification never did. Reverts to `outstanding` (not
        # `finding` -- an expired-on-file reply isn't a disqualifying determination for the
        # Clinical Director to judge, it's stale evidence needing a fresh one, the same category
        # resolve_licensure already puts a lapsed licence in). No real case in the office's three
        # batches has an expiry_date before any batch's as_of (checked across all three
        # certification-replies.csv files) -- implemented from the interview's own stated scenario
        # directly, not from an observed failure.
        expiry = _parse_date(reply.get("expiry_date") or "")
        if expiry is not None and expiry < _parse_date(as_of):
            all_confirmed = False
            action_items.append(
                ActionItem(
                    item="Certification for {} expired {}; needs re-verification as of {}".format(
                        cred.get("issuer", cred.get("declaration_id")), reply.get("expiry_date"), as_of
                    ),
                    owner="Medical Services Professional",
                )
            )
    if all_confirmed:
        return ElementResult(state="resolved")
    return ElementResult(state="outstanding", action_items=action_items)


def resolve_references(
    referees, peer_reference_replies, verification_attempts, as_of, rules, currency_date=None
) -> ElementResult:
    required = rules["references.required_count"]
    staleness_years = rules["references.staleness_years"]
    max_attempts = rules["verification.attempt_max_count"]
    min_spacing = rules["verification.attempt_min_spacing_days"]
    as_of_date = _parse_date(as_of)
    # LARK-REF-2026.1, "Currency": "A reference is current if the signature date is within two
    # years of the date the file is presented to the Governing Body... not the date we receive
    # the form" -- and not the batch's export date either. `currency_date` is the latest
    # Governing Body decision_date on file for this revision (process_application computes it);
    # before any such decision exists, there is no presentation date yet, so `as_of` is the best
    # available stand-in -- the same fallback already used for LARK-PRIV's "decision date" checks.
    currency_date_parsed = _parse_date(currency_date) if currency_date else as_of_date
    action_items = []
    qualifying_count = 0
    for referee in referees:
        reply = next(
            (r for r in peer_reference_replies if r.get("referee_id") == referee.get("referee_id")), None
        )
        if reply is None:
            # rules.md documents the 3-attempts/21-days cadence as applying to references too --
            # silence after the attempt ceiling must escalate the same way education/experience
            # already do, not sit as a generic "chase" message forever (real cases:
            # REF-1401/APP-2026-014, REF-2302/APP-2026-025, each with logged attempts and no reply).
            referee_label = referee.get("referee_name", referee.get("referee_id"))
            attempts = sorted(
                (
                    a
                    for a in verification_attempts
                    if a.get("subject_ref") == referee.get("referee_id") and a.get("element") == "peer-reference"
                ),
                key=lambda a: a["attempt_date"],
            )
            if len(attempts) >= max_attempts:
                action_items.append(
                    ActionItem(
                        item="references source {} has not replied after {} attempts; silence is not a pass".format(
                            referee_label, max_attempts
                        ),
                        owner="Medical Services Professional",
                    )
                )
            else:
                due = None
                if attempts:
                    due = _add_days(_parse_date(attempts[-1]["attempt_date"]), min_spacing).isoformat()
                action_items.append(
                    ActionItem(
                        item="Chase peer reference reply from {}".format(referee_label),
                        owner="Medical Services Professional",
                        due=due,
                    )
                )
            continue
        if reply.get("related_or_partner") == "Yes":
            action_items.append(
                ActionItem(
                    item="Reference from {} is a relative/partner and does not count; name a substitute referee".format(
                        referee.get("referee_name", referee.get("referee_id"))
                    ),
                    owner="Applicant",
                )
            )
            continue
        signature_date = _parse_date(reply.get("signature_date") or "")
        if signature_date is not None:
            stale_after = signature_date.replace(year=signature_date.year + staleness_years)
            if currency_date_parsed >= stale_after:
                action_items.append(
                    ActionItem(
                        item="Reference from {} signed {} is no longer current; refresh it".format(
                            referee.get("referee_name", referee.get("referee_id")), reply.get("signature_date")
                        ),
                        owner="Medical Services Professional",
                    )
                )
                continue
        qualifying_count += 1
    if qualifying_count >= required:
        return ElementResult(state="resolved")
    return ElementResult(state="outstanding", action_items=action_items)


def resolve_gaps(application_id, history, letters, rules) -> ElementResult:
    threshold = rules["intake.unexplained_gap_days"]
    entries = sorted((e for e in history if e.get("from_date")), key=lambda e: e["from_date"])
    for earlier, later in zip(entries, entries[1:]):
        gap_start_edge = _parse_date(earlier.get("to_date") or "")
        gap_end_edge = _parse_date(later["from_date"])
        if gap_start_edge is None or gap_end_edge is None:
            continue
        gap_days = (gap_end_edge - gap_start_edge).days - 1
        if gap_days < threshold:
            continue
        gap_start = _add_days(gap_start_edge, 1)
        gap_end = _add_days(gap_end_edge, -1)
        if _gap_is_explained(application_id, gap_start, gap_end, letters):
            return ElementResult(
                state="finding",
                action_items=[
                    ActionItem(
                        item="Clinical Director: is the explanation for the gap {} to {} satisfactory?".format(
                            gap_start.isoformat(), gap_end.isoformat()
                        ),
                        owner="Clinical Director",
                    )
                ],
                evidence={"gap_from": gap_start.isoformat(), "gap_to": gap_end.isoformat()},
            )
    return ElementResult(state="resolved")


def resolve_elements(
    *,
    application_id,
    history,
    credentials,
    referees,
    verification_replies,
    verification_attempts,
    licence_lookup_wa,
    licence_lookup_other,
    certification_replies,
    peer_reference_replies,
    letters,
    as_of,
    rules,
    app_row=None,
    references_currency_date=None,
) -> Dict[str, ElementResult]:
    # LARK-APP-2026.1, Section D: entry_type is "medical-school, residency, fellowship, or
    # other" -- fellowship was never included here, so a declared fellowship entry would never
    # be verified as education at all. No real application in office-exports/ currently declares
    # one (confirmed across all three batches), so this does not change any batch's sealed output.
    education_entries = [h for h in history if h.get("entry_type") in ("medical-school", "residency", "fellowship")]
    experience_entries = [h for h in history if h.get("entry_type") in ("employment", "teaching")]
    return {
        "licensure": resolve_licensure(credentials, licence_lookup_wa, licence_lookup_other, as_of, app_row=app_row),
        "education": resolve_attempt_tracked_element(
            "education", "education-and-training", education_entries, verification_replies, verification_attempts, as_of, rules,
            all_history_entries=history,
        ),
        "experience": resolve_attempt_tracked_element(
            "experience", "affiliation-and-employment", experience_entries, verification_replies, verification_attempts, as_of, rules
        ),
        "certification": resolve_certification(credentials, certification_replies, as_of),
        "references": resolve_references(
            referees, peer_reference_replies, verification_attempts, as_of, rules, currency_date=references_currency_date
        ),
        "gaps": resolve_gaps(application_id, history, letters, rules),
    }


def detect_discrepancies(history, verification_replies) -> List[dict]:
    discrepancies = []
    for entry in history:
        reply = next(
            (r for r in verification_replies if r.get("entry_id") == entry.get("entry_id")), None
        )
        if reply is None:
            continue
        for field_name, verified_key in (("from_date", "verified_from"), ("to_date", "verified_to")):
            verified_value = reply.get(verified_key)
            declared_value = entry.get(field_name)
            if verified_value and declared_value and verified_value != declared_value:
                discrepancies.append(
                    {
                        "entry_id": entry.get("entry_id"),
                        "field": field_name,
                        "declared": declared_value,
                        "verified": verified_value,
                    }
                )
    return discrepancies


def detect_credential_discrepancies(
    credentials, licence_lookup_wa, licence_lookup_other, certification_replies
) -> List[dict]:
    # Interview, 02:23 PM: "I compare the information declared on the application with... all
    # completed verifications. Where any discrepancy arises among these sources... I write to the
    # applicant naming both values." detect_discrepancies above only ever covered
    # declared_history's dates against verification_replies -- declared_credentials (licence and
    # certification) were never compared against their own independent sources
    # (licence-lookup-*.csv / certification-replies.csv) at all. Extended here to
    # declared_issue_date only.
    #
    # Deliberately NOT comparing declared_expiry_date: real case APP-2026-040's WA licence
    # (MD60096330) renewed between batch 2 and batch 3 -- expirationdate moved from 2026-04-10 to
    # 2028-04-30 in the board's own lookup, while firstissuedate stayed fixed at 2011-06-27 across
    # all three batches. An expiry date is a live, forward-moving fact the board's own record
    # keeps current; the application's declared_expiry_date is a frozen snapshot from intake.
    # Comparing them would flag every routine renewal after the original application as a false
    # discrepancy requiring applicant explanation, when nothing was ever misdeclared -- time just
    # passed. (Evidence genuinely *aging* while a file waits is a different, already-handled
    # concern: resolve_licensure and resolve_certification both compare the verified expiry
    # against `as_of` directly, reverting to `outstanding` rather than raising a false
    # discrepancy.) Issue date has no such problem -- it's fixed at first issuance and never
    # moves, confirmed by APP-2026-040's own data above.
    #
    # Deliberately NOT comparing declared_status against the verified status text: the
    # application form and the board's own reply use different vocabularies for the same fact
    # (the application declares "Board certified", the board replies "Active" -- confirmed across
    # every one of the office's three batches; only the one genuine status disagreement,
    # APP-2026-027's American Board of Surgery certification, is already correctly handled as a
    # `finding` routed to the Clinical Director via resolve_certification's own status check,
    # matching the office's own letter framing it as a threshold eligibility question, not
    # something the applicant resolves in writing). Comparing status text directly would have
    # flagged nearly every certification in the office's caseload as a false discrepancy.
    #
    # No real case in the office's three batches has an issue_date mismatch (checked across all
    # 87 declared-credentials rows with a matching lookup/reply) -- implemented from the
    # interview's own general reconciliation rule, not from an observed failure.
    discrepancies = []
    licence_lookups = licence_lookup_wa + licence_lookup_other
    for cred in credentials:
        if cred.get("credential_class") == "licence":
            match = next(
                (
                    row
                    for row in licence_lookups
                    if row.get("credentialnumber") == cred.get("number_declared")
                    or row.get("licence_number") == cred.get("number_declared")
                ),
                None,
            )
            if match is None:
                continue
            verified_issue_date = match.get("firstissuedate") or match.get("issue_date")
        elif cred.get("credential_class") == "certification":
            reply = next(
                (r for r in certification_replies if r.get("declaration_id") == cred.get("declaration_id")), None
            )
            if reply is None:
                continue
            verified_issue_date = reply.get("initial_certification_date")
        else:
            continue
        declared_value = cred.get("declared_issue_date")
        if verified_issue_date and declared_value and verified_issue_date != declared_value:
            discrepancies.append(
                {
                    "declaration_id": cred.get("declaration_id"),
                    "credential_class": cred.get("credential_class"),
                    "field": "declared_issue_date",
                    "declared": declared_value,
                    "verified": verified_issue_date,
                }
            )
    return discrepancies


# docs/office-documents/LARK-PRIV-2026.1-privilege-criteria.md, "The twelve privilege groups"
# table and "How the office applies the table" (rules 1-6; rule 7, current experience, is
# deliberately not encoded here -- see detect_eligibility_mismatch below). Each group: the
# (board_code, certificate_specialty) pairs from certification-replies.csv that support it, the
# minimum training duration in months, the keyword(s) to match a verified residency's declared
# `role` text against, and whether the board-eligible exception (rule 4) applies to this group.
# PRIV-CARD alone also carries its rule-5 compound requirement (a fellowship plus the internal
# medicine residency that precedes it).
_PRIVILEGE_CRITERIA = {
    "PRIV-FM": {"boards": {("ABFM", "Family Medicine"), ("AOBFP", "Family Practice")}, "training_months": 36, "training_keywords": ("family medicine",), "board_eligible": True},
    "PRIV-IM": {"boards": {("ABIM", "Internal Medicine"), ("AOBIM", "Internal Medicine")}, "training_months": 36, "training_keywords": ("internal medicine",), "board_eligible": True},
    "PRIV-HOSP": {
        "boards": {
            ("ABIM", "Internal Medicine"),
            ("ABIM", "Internal Medicine with Focused Practice in Hospital Medicine"),
            ("ABFM", "Family Medicine"),
            ("AOBIM", "Internal Medicine"),
        },
        "training_months": 36,
        "training_keywords": ("internal medicine", "family medicine"),
        "board_eligible": True,
    },
    "PRIV-CARD": {
        "boards": {("ABIM", "Cardiovascular Disease"), ("AOBIM", "Cardiology")},
        "training_months": 36,
        "training_keywords": None,
        "board_eligible": False,
        "fellowship_antecedent_keywords": ("internal medicine",),
    },
    "PRIV-EM": {"boards": {("ABEM", "Emergency Medicine"), ("AOBEM", "Emergency Medicine")}, "training_months": 36, "training_keywords": ("emergency medicine",), "board_eligible": False},
    "PRIV-GS": {"boards": {("ABS", "Surgery"), ("AOBS", "General Surgery")}, "training_months": 60, "training_keywords": ("general surgery",), "board_eligible": False},
    "PRIV-OBG": {"boards": {("ABOG", "Obstetrics and Gynecology"), ("AOBOG", "Obstetrics and Gynecology")}, "training_months": 48, "training_keywords": ("obstetrics and gynecology",), "board_eligible": False},
    "PRIV-PED": {"boards": {("ABP", "Pediatrics"), ("AOBP", "Pediatrics")}, "training_months": 36, "training_keywords": ("pediatrics",), "board_eligible": True},
    "PRIV-ANES": {"boards": {("ABA", "Anesthesiology"), ("AOBA", "Anesthesiology")}, "training_months": 48, "training_keywords": ("anesthesiology",), "board_eligible": False},
    "PRIV-RAD": {"boards": {("ABR", "Diagnostic Radiology"), ("AOBR", "Diagnostic Radiology")}, "training_months": 48, "training_keywords": ("diagnostic radiology",), "board_eligible": False},
    "PRIV-PSY": {"boards": {("ABPN", "Psychiatry"), ("AOBNP", "Psychiatry")}, "training_months": 48, "training_keywords": ("psychiatry",), "board_eligible": False},
    "PRIV-ORTHO": {"boards": {("ABOS", "Orthopaedic Surgery"), ("AOBOS", "Orthopedic Surgery")}, "training_months": 60, "training_keywords": ("orthopaedic surgery",), "board_eligible": False},
}

_BOARD_ELIGIBLE_END_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _training_months(from_date_str, to_date_str, as_of):
    # office-note-2026-03-16-export-format.md: "A date range is inclusive at both ends." A
    # residency declared 2010-07-01 to 2013-06-30 is exactly 36 months, not 35 -- the inclusive
    # end day completes the final month.
    from_date = _parse_date(from_date_str)
    to_date = _parse_date(to_date_str) if to_date_str else _parse_date(as_of)
    if from_date is None or to_date is None:
        return 0
    return (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month) + 1


def _verified_training_months(history, verification_replies, keywords, entry_types, as_of):
    best = 0
    for entry in history:
        if entry.get("entry_type") not in entry_types:
            continue
        role = (entry.get("role") or "").lower()
        if keywords and not any(k in role for k in keywords):
            continue
        confirmed = any(
            r.get("entry_id") == entry.get("entry_id")
            and r.get("element") == "education-and-training"
            and r.get("outcome") in ("confirmed", "confirmed-with-discrepancy")
            for r in verification_replies
        )
        if not confirmed:
            continue
        best = max(best, _training_months(entry.get("from_date"), entry.get("to_date"), as_of))
    return best


def _privilege_group_supported(code, declared_credentials, certification_replies, history, verification_replies, as_of):
    criteria = _PRIVILEGE_CRITERIA.get(code)
    if criteria is None:
        # An unpublished or retired code isn't this Skill's to invent a rule for; don't claim it
        # unsupported on a guess.
        return True
    as_of_date = _parse_date(as_of)
    active_support = False
    board_eligible_support = False
    for cred in declared_credentials:
        if cred.get("credential_class") != "certification":
            continue
        reply = next((r for r in certification_replies if r.get("declaration_id") == cred.get("declaration_id")), None)
        if reply is None:
            continue
        if (reply.get("board_code"), reply.get("certificate_specialty")) not in criteria["boards"]:
            continue
        status = (reply.get("certification_status") or "").lower()
        if status == "active":
            active_support = True
        elif criteria["board_eligible"] and status == "not certified":
            # Rule 4: accepted only for PRIV-FM/IM/HOSP/PED, only when the board confirms in
            # writing (a reason stated in the reply's own notes, naming "eligible") and states an
            # end date that is still in the future. Real case: CR-01000/APP-2026-010 -- "Candidate
            # in good standing; board eligible through 2027-06-30."
            notes = (reply.get("notes") or "").lower()
            match = _BOARD_ELIGIBLE_END_DATE_RE.search(reply.get("notes") or "")
            if "eligible" in notes and match:
                end_date = _parse_date(match.group(1))
                if end_date is not None and end_date > as_of_date:
                    board_eligible_support = True
    if not (active_support or board_eligible_support):
        return False
    if "fellowship_antecedent_keywords" in criteria:
        # Rule 5: PRIV-CARD requires both the fellowship and the internal medicine residency that
        # precedes it. No real application in office-exports/ has a verified fellowship entry at
        # all (entry_type "fellowship" never appears in any of the three batches' declared-history
        # rows) -- real case APP-2026-026 requests PRIV-CARD with only an Internal Medicine
        # residency and no fellowship, so it is correctly unsupported under this rule.
        fellowship_months = _verified_training_months(history, verification_replies, None, ("fellowship",), as_of)
        antecedent_months = _verified_training_months(
            history, verification_replies, criteria["fellowship_antecedent_keywords"], ("residency",), as_of
        )
        return fellowship_months >= criteria["training_months"] and antecedent_months > 0
    training_months = _verified_training_months(history, verification_replies, criteria["training_keywords"], ("residency",), as_of)
    return training_months >= criteria["training_months"]


def detect_eligibility_mismatch(priv_requests, history, credentials, certification_replies, as_of, verification_replies) -> bool:
    # Rule 6: "When nothing the applicant holds supports any requested group, this is a threshold
    # eligibility question... raised to the Clinical Director... on what has been verified at the
    # export date." Only fires when NONE of the requested groups are supported -- if even one is,
    # the Skill raises nothing (the office's own committee review handles any other unsupported
    # group from here, per rule 2; this function only ever implements the Skill's own narrower
    # role under rule 6). Rule 7 (current experience) is deliberately excluded from every check
    # above -- "The current-experience column is not the office's to apply."
    if not priv_requests:
        return False
    return not any(
        _privilege_group_supported(
            request.get("privilege_code"), credentials, certification_replies, history, verification_replies, as_of
        )
        for request in priv_requests
    )


def detect_ppq_findings(disclosures) -> bool:
    return any(d.get("answer") == "Yes" for d in disclosures)


def detect_ppq_verification_mismatch(
    disclosures, credentials, licence_lookup_wa, licence_lookup_other, dispositions=None, reply_letters=None
):
    # LARK-APP-2026.1, Section I: "If a verification the office receives shows that a Yes was
    # owed and a No was given, the office will contact you to confirm the answer before the file
    # goes any further." Real case: APP-2026-015 declared PPQ-1 "No" while the WA board's own
    # lookup shows actiontaken "Yes" (a stipulated agreement); the office's own
    # confirm-disclosure letter is this exact procedure in action. Scoped to PPQ-1 only -- it is
    # the one professional-practice question with a verification source directly checkable from
    # this export (a licence's board action); none of the other seven PPQs have a comparably
    # verifiable cross-reference in the data (there is no data source that could confirm or
    # contradict, say, a past criminal conviction or a federal exclusion).
    #
    # Real bug, caught by the project owner tracing APP-2026-015's full letter trail:
    # application-disclosures.csv's declared answer never changes once filed
    # (office-note-2026-03-16-export-format.md: a correction arrives as correspondence, not a new
    # application revision), so a check comparing only declared-vs-verified has no way to ever
    # stop firing -- even after the Clinical Director's disposition already says she read the
    # applicant's written confirmation and acted on it
    # (office-exports/batch-03/dispositions/2026-05-06_disposition_APP-2026-015.md). Stops once
    # either human-record signal exists: any disposition on file for the application (the Skill
    # defers to the Clinical Director's review, the same "consume the human record once it
    # exists" precedent apply_dispositions/admit_disposition already follow), or, short of that,
    # an inbound confirm-disclosure-reply letter from the applicant
    # (office-exports/batch-03/letters/2026-04-20_confirm-disclosure-reply_APP-2026-015.md).
    if dispositions:
        return []
    if any((letter or {}).get("letter_type") == "confirm-disclosure-reply" for letter in (reply_letters or [])):
        return []
    mismatches = []
    ppq1 = next((d for d in disclosures if d.get("question_code") == "PPQ-1"), None)
    if ppq1 is None or ppq1.get("answer") != "No":
        return mismatches
    lookups = licence_lookup_wa + licence_lookup_other
    for cred in credentials:
        if cred.get("credential_class") != "licence":
            continue
        match = next(
            (
                row
                for row in lookups
                if row.get("credentialnumber") == cred.get("number_declared")
                or row.get("licence_number") == cred.get("number_declared")
            ),
            None,
        )
        if match is None:
            continue
        action = match.get("actiontaken") or match.get("disciplinary_action") or "No"
        if action not in ("No", "None reported"):
            mismatches.append({"question_code": "PPQ-1", "declared": "No", "verified": action})
    return mismatches


# docs/office-documents/LARK-AUTH-2026.1-reserved-authority.md, "Who may record what" table.
# Session-decision note previously in rules.md ("the interview never covered the authority
# roster or decision-admission criteria") was wrong -- this document is exactly that roster, just
# not read until 2026-10-05. "not-recommended" is this project's own normalized spelling for the
# manual's plain-English "not recommended" outcome (consistent with the hyphenated style of the
# other outcome strings already in use, e.g. "deferred-pending-information") -- no real decision
# document in office-exports/ ever uses this outcome, so the exact raw string the office would
# write is unconfirmed; admit_decision normalizes spaces to hyphens before comparing so either
# spelling is accepted.
_VALID_OUTCOMES_BY_BODY = {
    "Credentials Committee": {"recommended", "not-recommended", "deferred-pending-information"},
    "Executive Committee of the Medical Staff": {"recommended", "not-recommended", "deferred-pending-information"},
    "Governing Body": {"approved", "approved-with-conditions", "deferred-pending-information", "denied"},
}

# docs/office-documents/LARK-AUTH-2026.1-reserved-authority.md, "Individual authority" table, plus
# the Governing Body's "Designation of record" paragraph for the Vice-Chair. Each body maps to the
# individual(s) who may record its outcomes, with the term (or, for the Vice-Chair, the specific
# calendar-year-2026 designation window) during which their signature is valid. Checked against
# the decision's own `decision_date` -- "did that person hold that role on the decision date,"
# per the document's opening line.
_AUTHORITY_ROSTER = {
    "Credentials Committee": [
        {"signatory": "Dr. Anneke Thorvald, MD", "role": "Chair, Credentials Committee", "term_start": "2025-07-01", "term_end": "2027-06-30"},
    ],
    "Executive Committee of the Medical Staff": [
        {"signatory": "Dr. Peter Vandermolen, MD", "role": "Chair, Executive Committee of the Medical Staff", "term_start": "2026-01-01", "term_end": "2027-12-31"},
    ],
    "Governing Body": [
        {"signatory": "Ms. Corinne Batiste", "role": "Chair, Governing Body", "term_start": "2025-01-01", "term_end": "2027-12-31"},
        {"signatory": "Mr. Desmond Ihejirika", "role": "Vice-Chair, Governing Body", "term_start": "2026-01-01", "term_end": "2026-12-31"},
    ],
}


def admit_decision(decision: dict, already_admitted_bodies=None):
    already_admitted_bodies = already_admitted_bodies or set()
    body = decision.get("body", "")
    outcome = (decision.get("outcome", "") or "").replace(" ", "-")
    signatory = decision.get("signatory", "")
    role = decision.get("role", "")

    valid_outcomes = _VALID_OUTCOMES_BY_BODY.get(body)
    if valid_outcomes is None:
        return False, "issuing body '{}' is not recognized".format(body)
    if outcome not in valid_outcomes:
        return False, "{} may not issue outcome '{}'".format(body, decision.get("outcome", ""))
    if not signatory:
        return False, "decision carries no named signatory"
    if not role:
        return False, "decision carries no signatory role"
    # LARK-AUTH-2026.1's own opening line: "A record's own claim of authority is not evidence of
    # it." A name+role the roster doesn't recognize for this body at all is refused regardless of
    # how plausible it looks.
    roster_entry = next(
        (r for r in _AUTHORITY_ROSTER.get(body, []) if r["signatory"] == signatory and r["role"] == role),
        None,
    )
    if roster_entry is None:
        return False, "{} is not recorded as {} for {}".format(signatory, role, body)
    decision_date = _parse_date(decision.get("decision_date") or "")
    if decision_date is None:
        return False, "decision carries no usable decision date to check against the authority roster"
    term_start = _parse_date(roster_entry["term_start"])
    term_end = _parse_date(roster_entry["term_end"])
    if not (term_start <= decision_date <= term_end):
        return False, "{} was outside their term ({} to {}) on {}".format(
            signatory, roster_entry["term_start"], roster_entry["term_end"], decision.get("decision_date")
        )
    if body in already_admitted_bodies:
        return False, "a decision from {} is already admitted for this application and revision".format(body)
    return True, None


def compute_activation(decision: dict, rules, as_of: str) -> Activation:
    cycle_years = rules["appointment.cycle_years"]
    effective = _parse_date(decision.get("effective_date") or decision.get("decision_date"))
    cycle_end = effective.replace(year=effective.year + cycle_years)
    as_of_date = _parse_date(as_of)
    active_at_export = effective <= as_of_date <= cycle_end
    return Activation(
        active_at_export=active_at_export,
        effective_date=effective.isoformat(),
        cycle_end=cycle_end.isoformat(),
        privileges=list(decision.get("privileges") or []),
    )


_PER_APP_ROW_TYPES = {
    "disclosures": "question_code",
    "declared_history": "entry_id",
    "declared_credentials": "declaration_id",
    "privilege_requests": "request_id",
    "peer_referees": "referee_id",
    "verification_replies": "reply_id",
    "verification_attempts": "attempt_id",
    "certification_replies": "reply_id",
    "peer_reference_replies": "reply_id",
    "correspondence": "letter_id",
}

_THROUGH_DATE_RE = re.compile(r"through (\d{4}-\d{2}-\d{2})")


def merge_rows(existing_rows, new_rows, key_field):
    merged = {row[key_field]: row for row in existing_rows if key_field in row and row[key_field]}
    for row in new_rows:
        if key_field in row and row[key_field]:
            merged[row[key_field]] = row
    return list(merged.values())


def parse_disposition_outcome(text: str) -> set:
    lowered = text.lower()
    labels = set()
    if "discontinue the application" in lowered and "do not discontinue" not in lowered:
        labels.add("discontinue")
    if "opportunity to amend" in lowered:
        labels.add("amend-offer")
    # "Present the file to the committee" is a routing instruction -- it says the file moves on,
    # not that the finding is immaterial. Only an actual determination clears a finding; a
    # disposition that routes the file onward while explicitly declining to recommend on it (real
    # case: APP-2026-015, "I make no recommendation on the privileges themselves") must NOT read
    # as cleared, or the engine ends up deciding protected judgment #2 (whether a finding is
    # disqualifying) by proxy.
    if any(
        phrase in lowered
        for phrase in (
            "sufficient and the file may proceed",
            "no bar to appointment",
        )
    ):
        labels.add("clear")
    return labels


# docs/office-documents/LARK-AUTH-2026.1-reserved-authority.md, "Individual authority" table.
# Dispositions carry recorded_by as one combined field ("<signatory>, <role>"), unlike decisions'
# separate signatory/role fields -- confirmed the exact format across all 5 real disposition
# documents.
_CLINICAL_DIRECTOR_RECORDED_BY = "Dr. Marguerite Oyelaran, MD, Clinical Director"
_CLINICAL_DIRECTOR_TERM = ("2025-07-01", "2027-06-30")


def admit_disposition(disposition):
    recorded_by = disposition.get("recorded_by", "")
    if recorded_by != _CLINICAL_DIRECTOR_RECORDED_BY:
        return False, "recorded by '{}', not the Clinical Director of record".format(recorded_by or "an unnamed person")
    date = _parse_date(disposition.get("date") or "")
    if date is None:
        return False, "disposition carries no usable date to check against the Clinical Director's term"
    term_start, term_end = (_parse_date(d) for d in _CLINICAL_DIRECTOR_TERM)
    if not (term_start <= date <= term_end):
        return False, "dated {}, outside the Clinical Director's term ({} to {})".format(
            disposition.get("date"), *_CLINICAL_DIRECTOR_TERM
        )
    return True, None


def apply_dispositions(elements, dispositions):
    elements = dict(elements)
    status_override = None
    action_items = []
    unmatched = False
    for disposition in sorted(dispositions, key=lambda d: d["date"]):
        admitted, reason = admit_disposition(disposition)
        if not admitted:
            # LARK-AUTH-2026.1's opening line, same as decision admission: "A record's own claim
            # of authority is not evidence of it." An inadmissible disposition is never applied --
            # not to clear a finding, not to discontinue -- it is raised to a human instead.
            unmatched = True
            action_items.append(
                ActionItem(
                    item="Disposition {} could not be admitted ({}); the Clinical Director must reissue or confirm it".format(
                        disposition["filename"], reason
                    ),
                    owner="Medical Services Professional",
                )
            )
            continue
        labels = parse_disposition_outcome(disposition["raw_text"])
        if "discontinue" in labels:
            status_override = "discontinued"
            action_items.append(
                ActionItem(
                    item="Notify applicant of discontinuance per disposition {}".format(disposition["filename"]),
                    owner="Medical Services Professional",
                )
            )
            continue
        flagged = [
            name
            for name, state in elements.items()
            if state in ("finding", "routed-to-clinical-director", "eligibility-question")
        ]
        if not flagged:
            continue
        if "clear" in labels:
            for name in flagged:
                elements[name] = "resolved"
        elif "amend-offer" in labels:
            action_items.append(
                ActionItem(
                    item="Applicant: amend the privilege request or provide further support per disposition {}".format(
                        disposition["filename"]
                    ),
                    owner="Applicant",
                )
            )
        else:
            unmatched = True
            action_items.append(
                ActionItem(
                    item="Disposition {} could not be automatically interpreted; a human must read it".format(
                        disposition["filename"]
                    ),
                    owner="Medical Services Professional",
                )
            )
    return elements, status_override, action_items, unmatched


def evaluate_decisions(revision, decisions_for_app):
    # Every decision the office ever issued for this application must appear in decision_records
    # -- one whose revision no longer matches the file's current revision (e.g. an unrelated
    # correction bumped the revision after the decision was issued) is refused with a reason and
    # queued for a human, never silently dropped (real data: APP-2026-036's Governing Body
    # approval for revision 1 would otherwise vanish once a later correction moved it to
    # revision 2 in the same batch).
    decision_records = []
    admitted_gb_outcome = None
    approval_decision_id = None
    activation_source = None
    action_items = []

    relevant = []
    for decision in decisions_for_app:
        if decision.get("revision") != revision:
            reason = "decision names revision {}; the file is now at revision {}".format(
                decision.get("revision"), revision
            )
            decision_records.append(Decision(decision_id=decision["decision_id"], admitted=False, reason=reason))
            action_items.append(
                ActionItem(
                    item="Confirm whether decision {} still applies now that the file is at revision {}".format(
                        decision["decision_id"], revision
                    ),
                    owner="Medical Services Professional",
                )
            )
            continue
        relevant.append(decision)

    # Only the chronologically latest decision from each body is a candidate for admission. A
    # real office sequence -- a Governing Body deferral, then later a Governing Body approval
    # once the applicant supplies what was missing -- must let the later decision win; the
    # earlier one is refused as superseded by it, never as an inadmissible "duplicate" (which
    # would wrongly block the normal resolution of a deferral).
    relevant_sorted = sorted(relevant, key=lambda d: d.get("decision_date") or "")
    latest_by_body = {}
    for decision in relevant_sorted:
        latest_by_body[decision.get("body")] = decision

    for decision in relevant_sorted:
        if latest_by_body.get(decision.get("body")) is not decision:
            newer = latest_by_body[decision.get("body")]
            reason = "superseded by a later decision from {} ({})".format(decision.get("body"), newer["decision_id"])
            decision_records.append(Decision(decision_id=decision["decision_id"], admitted=False, reason=reason))
            continue
        admitted, reason = admit_decision(decision)
        decision_records.append(Decision(decision_id=decision["decision_id"], admitted=admitted, reason=reason))
        if admitted:
            if decision["body"] == "Governing Body":
                admitted_gb_outcome = decision["outcome"]
                if decision["outcome"] in ("approved", "approved-with-conditions"):
                    approval_decision_id = decision["decision_id"]
                    activation_source = decision
                elif decision["outcome"] in ("denied", "deferred-pending-information") and decision.get("reason"):
                    # A deferral or denial's stated reason names exactly what is owed or why the
                    # file was denied -- a file on a Governing Body hold must not sit with an
                    # empty action_queue (real case: APP-2026-034's deferral, "one further peer
                    # reference from a referee outside the applicant's current group practice").
                    action_items.append(
                        ActionItem(
                            item="Governing Body {}: {}".format(decision["outcome"], decision["reason"]),
                            owner="Medical Services Professional",
                        )
                    )
        else:
            # Any refusal -- wrong body, missing signatory, a duplicate -- leaves a decision that
            # needs a human's attention to get reissued correctly (real case: MEC-2026-036, the
            # Executive Committee issuing "approved", which only the Governing Body may).
            action_items.append(
                ActionItem(
                    item="Decision {} was refused ({}); confirm with the issuing body whether a corrected decision is needed".format(
                        decision["decision_id"], reason
                    ),
                    owner="Medical Services Professional",
                )
            )
    has_inadmissible = any(not d.admitted for d in decision_records)
    return decision_records, admitted_gb_outcome, approval_decision_id, activation_source, has_inadmissible, action_items


def extract_monitored_conditions(store, activation_decision=None) -> List[MonitoredCondition]:
    conditions = []
    for letter in store.get("letters", []):
        if letter.get("letter_type") != "board-action":
            continue
        match = _THROUGH_DATE_RE.search(letter.get("raw_text", ""))
        if match:
            conditions.append(
                MonitoredCondition(condition="Board-ordered monitoring programme in force", due=match.group(1))
            )
    # An approved-with-conditions Governing Body decision states its own conditions directly
    # (parsed by scripts.parsers._load_decisions into the decision's "conditions" list) -- these
    # are real dated obligations (e.g. a licence re-verification deadline) and must appear here,
    # or "active-with-conditions" ends up asserting a status its own payload doesn't back up.
    if activation_decision is not None:
        for condition in activation_decision.get("conditions", []):
            conditions.append(MonitoredCondition(condition=condition["condition"], due=condition["due"]))
    return conditions


def compute_status(*, intake_status, elements, admitted_gb_outcome, has_inadmissible_decision, activation):
    if intake_status != "complete":
        return intake_status
    # An admitted Governing Body decision is the office's real authority and governs the status
    # regardless of whether this engine's own element tracking still shows a lingering finding --
    # real batch data surfaced files the Governing Body approved while one element (e.g. a
    # certification lapse no disposition ever explicitly cleared) still read "finding" here. That
    # finding belongs in the action queue, not in blocking an already-decided file at
    # "in-verification" forever. Only in the ABSENCE of an admitted Governing Body outcome does
    # the status enum's precedence order apply: decision-inadmissible and packet-presentable both
    # require every element resolved first; short of that, the file is simply in-verification.
    if admitted_gb_outcome == "denied":
        return "denied"
    if admitted_gb_outcome == "deferred-pending-information":
        return "deferred"
    if admitted_gb_outcome in ("approved", "approved-with-conditions"):
        if activation is not None and activation.active_at_export:
            return "active-with-conditions" if admitted_gb_outcome == "approved-with-conditions" else "active"
        return "approved-not-yet-effective"
    if not all(state == "resolved" for state in elements.values()):
        return "in-verification"
    if has_inadmissible_decision:
        return "decision-inadmissible"
    return "packet-presentable"


def _action_item_from_dict(d: dict) -> ActionItem:
    return ActionItem(item=d["item"], owner=d["owner"], due=d.get("due"))


def _decision_from_dict(d: dict) -> Decision:
    return Decision(decision_id=d["decision_id"], admitted=d["admitted"], reason=d.get("reason"))


def _monitored_condition_from_dict(d: dict) -> MonitoredCondition:
    return MonitoredCondition(condition=d["condition"], due=d["due"])


# The real edge case this guards against: resolve_elements can already have found something
# genuinely wrong with an element (a board action, an inactive certification, a credential-date
# discrepancy) before any of discrepancy-detection, eligibility-mismatch, or PPQ-finding ever run.
# Each of those three later checks used to overwrite the element's compact state unconditionally
# the moment it fired -- so whichever concern was detected *last* in process_application's fixed
# code order silently erased whatever an earlier concern had already recorded there, even though
# every concern's own action-queue item kept being added regardless (the queue never lost
# anything; only this compact summary field did). _flag_element only ever claims an element that
# nothing has already flagged (`resolved`/`outstanding`) -- the first genuine concern found wins
# the slot, later ones still queue their own action item, and nothing is silently discarded.
_UNFLAGGED_ELEMENT_STATES = {"resolved", "outstanding"}


def _flag_element(elements, name, new_state):
    if elements.get(name) in _UNFLAGGED_ELEMENT_STATES:
        elements[name] = new_state


def process_application(application_id, batch, ledger, rules, as_of):
    entry = get_application_entry(ledger, application_id)
    warnings: List[str] = []

    if entry.get("status") in ("withdrawn", "discontinued"):
        # Once terminal, this record is a frozen snapshot of what was true when the status was
        # set -- its decisions/action_queue/monitored_conditions must be carried forward from the
        # ledger, not defaulted to empty, or a real item (e.g. "Notify applicant of
        # discontinuance ...") silently vanishes the very next batch (real case: APP-2026-029).
        elements = entry.get("elements") or {name: "outstanding" for name in ELEMENT_NAMES}
        record = ApplicationRecord(
            application_id=application_id,
            revision=entry.get("revision") or 1,
            status=entry["status"],
            elements=elements,
            packet_presentable=False,
            decisions=[_decision_from_dict(d) for d in entry.get("decisions", [])],
            approval_decision_id=entry.get("approval_decision_id"),
            monitored_conditions=[
                _monitored_condition_from_dict(m) for m in entry.get("monitored_conditions", [])
            ],
            action_queue=[_action_item_from_dict(a) for a in entry.get("action_queue", [])],
        )
        return record, warnings

    app_rows_this_batch = filter_rows(batch.applications, application_id=application_id)
    if app_rows_this_batch:
        app_row = max(app_rows_this_batch, key=lambda r: int(r["revision"]))
        entry["last_application_row"] = app_row
        entry["revision"] = int(app_row["revision"])
    app_row = entry.get("last_application_row") or {}
    revision = entry.get("revision") or 1

    store = entry.setdefault("revision_data", {})
    for row_type, key_field in _PER_APP_ROW_TYPES.items():
        batch_rows = [r for r in getattr(batch, row_type) if r.get("application_id") == application_id]
        store[row_type] = merge_rows(store.get(row_type, []), batch_rows, key_field)
    new_decisions = [d for d in batch.decisions.values() if d.get("application_id") == application_id]
    store["decisions"] = merge_rows(store.get("decisions", []), new_decisions, "decision_id")
    new_dispositions = [d for d in batch.dispositions.values() if d.get("application_id") == application_id]
    store["dispositions"] = merge_rows(store.get("dispositions", []), new_dispositions, "filename")
    new_letters = [l for l in batch.letters.values() if l.get("application_id") == application_id]
    store["letters"] = merge_rows(store.get("letters", []), new_letters, "filename")

    withdrawal = next((l for l in store["letters"] if l.get("letter_type") == "withdrawal"), None)
    if withdrawal is not None:
        elements = {name: "outstanding" for name in ELEMENT_NAMES}
        entry["status"] = "withdrawn"
        entry["elements"] = elements
        entry["decisions"] = []
        entry["action_queue"] = []
        entry["monitored_conditions"] = []
        record = ApplicationRecord(
            application_id=application_id, revision=revision, status="withdrawn",
            elements=elements, packet_presentable=False,
        )
        return record, warnings

    intake = evaluate_intake(
        application_id=application_id,
        app_row=app_row,
        disclosures=store.get("disclosures", []),
        history=store.get("declared_history", []),
        credentials=store.get("declared_credentials", []),
        priv_requests=store.get("privilege_requests", []),
        referees=store.get("peer_referees", []),
        correspondence=store.get("correspondence", []),
        letters=store.get("letters", []),
        as_of=as_of,
        rules=rules,
    )

    if intake.status != "complete":
        elements = {name: "outstanding" for name in ELEMENT_NAMES}
        if intake.status == "returned-incomplete":
            elements["gaps"] = "return-incomplete"
        entry["status"] = intake.status
        entry["elements"] = elements
        record = ApplicationRecord(
            application_id=application_id, revision=revision, status=intake.status,
            elements=elements, packet_presentable=False, action_queue=intake.action_items,
        )
        return record, warnings

    gb_presentation_dates = [
        d.get("decision_date")
        for d in store.get("decisions", [])
        if d.get("body") == "Governing Body" and d.get("revision") == revision and d.get("decision_date")
    ]
    references_currency_date = max(gb_presentation_dates) if gb_presentation_dates else None

    elements_result = resolve_elements(
        application_id=application_id,
        history=store.get("declared_history", []),
        credentials=store.get("declared_credentials", []),
        referees=store.get("peer_referees", []),
        verification_replies=store.get("verification_replies", []),
        verification_attempts=store.get("verification_attempts", []),
        licence_lookup_wa=ledger.get("licence_lookup_wa", []),
        licence_lookup_other=ledger.get("licence_lookup_other", []),
        certification_replies=store.get("certification_replies", []),
        peer_reference_replies=store.get("peer_reference_replies", []),
        letters=store.get("letters", []),
        as_of=as_of,
        rules=rules,
        app_row=app_row,
        references_currency_date=references_currency_date,
    )
    elements = {name: result.state for name, result in elements_result.items()}
    action_queue: List[ActionItem] = []
    for result in elements_result.values():
        action_queue.extend(result.action_items)

    discrepancies = detect_discrepancies(store.get("declared_history", []), store.get("verification_replies", []))
    if discrepancies:
        touched_ids = {d["entry_id"] for d in discrepancies}
        touched_types = {
            row.get("entry_type") for row in store.get("declared_history", []) if row.get("entry_id") in touched_ids
        }
        if touched_types & {"medical-school", "residency"}:
            _flag_element(elements, "education", "discrepancy")
        if touched_types & {"employment", "teaching"}:
            _flag_element(elements, "experience", "discrepancy")
        for d in discrepancies:
            action_queue.append(
                ActionItem(
                    item="Discrepancy on {}: declared {} is {}, source says {}; applicant must resolve in writing or amend".format(
                        d["entry_id"], d["field"], d["declared"], d["verified"]
                    ),
                    owner="Applicant",
                )
            )

    credential_discrepancies = detect_credential_discrepancies(
        store.get("declared_credentials", []),
        ledger.get("licence_lookup_wa", []),
        ledger.get("licence_lookup_other", []),
        store.get("certification_replies", []),
    )
    if credential_discrepancies:
        touched_classes = {d["credential_class"] for d in credential_discrepancies}
        if "licence" in touched_classes:
            _flag_element(elements, "licensure", "discrepancy")
        if "certification" in touched_classes:
            _flag_element(elements, "certification", "discrepancy")
        for d in credential_discrepancies:
            action_queue.append(
                ActionItem(
                    item="Discrepancy on {}: declared {} is {}, source says {}; applicant must resolve in writing or amend".format(
                        d["declaration_id"], d["field"], d["declared"], d["verified"]
                    ),
                    owner="Applicant",
                )
            )

    if detect_eligibility_mismatch(
        store.get("privilege_requests", []),
        store.get("declared_history", []),
        store.get("declared_credentials", []),
        store.get("certification_replies", []),
        as_of,
        store.get("verification_replies", []),
    ):
        _flag_element(elements, "certification", "eligibility-question")
        action_queue.append(
            ActionItem(
                item="Nothing on file supports the privilege requested; Clinical Director review needed",
                owner="Clinical Director",
            )
        )

    if detect_ppq_findings(store.get("disclosures", [])):
        _flag_element(elements, "licensure", "finding")
        action_queue.append(
            ActionItem(
                item="A professional practice question was answered Yes; Clinical Director must judge whether this finding is disqualifying",
                owner="Clinical Director",
            )
        )

    for mismatch in detect_ppq_verification_mismatch(
        store.get("disclosures", []),
        store.get("declared_credentials", []),
        ledger.get("licence_lookup_wa", []),
        ledger.get("licence_lookup_other", []),
        dispositions=store.get("dispositions", []),
        reply_letters=store.get("letters", []),
    ):
        action_queue.append(
            ActionItem(
                item=(
                    "Declared {} to {} but a source reports '{}'; confirm the answer in writing "
                    "or submit a revision".format(
                        mismatch["declared"], mismatch["question_code"], mismatch["verified"]
                    )
                ),
                owner="Applicant",
            )
        )

    elements, status_override, disposition_action_items, unmatched = apply_dispositions(
        elements, store.get("dispositions", [])
    )
    action_queue.extend(disposition_action_items)
    if unmatched:
        warnings.append(
            "Application {} has a Clinical Director disposition that could not be automatically interpreted".format(
                application_id
            )
        )

    if status_override == "discontinued":
        entry["status"] = "discontinued"
        entry["elements"] = elements
        entry["decisions"] = []
        entry["action_queue"] = [item.to_dict() for item in action_queue]
        entry["monitored_conditions"] = []
        record = ApplicationRecord(
            application_id=application_id, revision=revision, status="discontinued",
            elements=elements, packet_presentable=False, action_queue=action_queue,
        )
        return record, warnings

    (
        decision_records,
        admitted_gb_outcome,
        approval_decision_id,
        activation_source,
        has_inadmissible,
        decision_action_items,
    ) = evaluate_decisions(revision, store.get("decisions", []))
    action_queue.extend(decision_action_items)
    activation = compute_activation(activation_source, rules, as_of) if activation_source is not None else None
    monitored_conditions = extract_monitored_conditions(store, activation_source)

    status = compute_status(
        intake_status="complete",
        elements=elements,
        admitted_gb_outcome=admitted_gb_outcome,
        has_inadmissible_decision=has_inadmissible,
        activation=activation,
    )
    packet_presentable = all(state == "resolved" for state in elements.values()) and admitted_gb_outcome is None

    entry["status"] = status
    entry["elements"] = elements
    entry["approval_decision_id"] = approval_decision_id
    entry["activation"] = activation.to_dict() if activation else None

    record = ApplicationRecord(
        application_id=application_id,
        revision=revision,
        status=status,
        elements=elements,
        packet_presentable=packet_presentable,
        decisions=decision_records,
        approval_decision_id=approval_decision_id,
        activation=activation,
        monitored_conditions=monitored_conditions,
        action_queue=action_queue,
    )
    return record, warnings


def process_batch(batch, ledger, rules, as_of):
    ledger["licence_lookup_wa"] = merge_rows(ledger.get("licence_lookup_wa", []), batch.licence_lookup_wa, "credentialnumber")
    ledger["licence_lookup_other"] = merge_rows(
        ledger.get("licence_lookup_other", []), batch.licence_lookup_other, "licence_number"
    )

    all_ids = sorted(set(batch.application_ids()) | set(ledger["applications"].keys()))
    records = []
    warnings: List[str] = []
    for application_id in all_ids:
        record, app_warnings = process_application(application_id, batch, ledger, rules, as_of)
        records.append(record)
        warnings.extend(app_warnings)
    return records, ledger, warnings
