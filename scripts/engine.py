from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from scripts.model import ActionItem


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
        missing.append(
            "at least {} peer referees with a working address each".format(required_referees)
        )
    for entry in history:
        if entry.get("entry_type") in ("employment", "teaching") and not (
            entry.get("contact_name") or entry.get("contact_email")
        ):
            missing.append(
                "a verification contact for {}".format(entry.get("organization", "a declared affiliation"))
            )
    return missing


def _gap_is_explained(application_id: str, gap_start: datetime.date, gap_end: datetime.date, correspondence) -> bool:
    start_label = gap_start.isoformat()
    end_label = gap_end.isoformat()
    for row in correspondence:
        if row.get("application_id") != application_id or row.get("direction") != "inbound":
            continue
        subject = row.get("subject", "")
        if start_label in subject and end_label in subject:
            return True
    return False


def unexplained_gap(application_id: str, history, correspondence, rules) -> Optional[Dict[str, object]]:
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
        if not _gap_is_explained(application_id, gap_start, gap_end, correspondence):
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
    as_of: str,
    rules,
) -> IntakeResult:
    gap = unexplained_gap(application_id, history, correspondence, rules)
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


def resolve_licensure(credentials, licence_lookup_wa, licence_lookup_other, as_of) -> ElementResult:
    licence_credentials = [c for c in credentials if c.get("credential_class") == "licence"]
    if not licence_credentials:
        return ElementResult(
            state="outstanding",
            action_items=[ActionItem(item="No licence declared to verify", owner="Medical Services Professional")],
        )
    as_of_date = _parse_date(as_of)
    lookups = licence_lookup_wa + licence_lookup_other
    for cred in licence_credentials:
        number = cred.get("number_declared")
        match = next(
            (
                row
                for row in lookups
                if row.get("credentialnumber") == number or row.get("licence_number") == number
            ),
            None,
        )
        if match is None:
            return ElementResult(
                state="outstanding",
                action_items=[
                    ActionItem(
                        item="No current board record found for licence {}".format(number),
                        owner="Medical Services Professional",
                    )
                ],
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


def resolve_attempt_tracked_element(
    element_name, element_label, history_entries, verification_replies, verification_attempts, as_of, rules
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
    action_items = []
    all_confirmed = True
    for entry in history_entries:
        entry_id = entry["entry_id"]
        confirmed = any(
            r.get("entry_id") == entry_id and r.get("element") == element_label and r.get("outcome") == "confirmed"
            for r in verification_replies
        )
        if confirmed:
            continue
        all_confirmed = False
        source_label = entry.get("organization", entry_id)
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
    if all_confirmed:
        return ElementResult(state="resolved")
    return ElementResult(state="outstanding", action_items=action_items)


def resolve_references(referees, peer_reference_replies, as_of, rules) -> ElementResult:
    required = rules["references.required_count"]
    staleness_years = rules["references.staleness_years"]
    as_of_date = _parse_date(as_of)
    action_items = []
    qualifying_count = 0
    for referee in referees:
        reply = next(
            (r for r in peer_reference_replies if r.get("referee_id") == referee.get("referee_id")), None
        )
        if reply is None:
            action_items.append(
                ActionItem(
                    item="Chase peer reference reply from {}".format(
                        referee.get("referee_name", referee.get("referee_id"))
                    ),
                    owner="Medical Services Professional",
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
            if as_of_date >= stale_after:
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


def resolve_gaps(application_id, history, correspondence, rules) -> ElementResult:
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
        if _gap_is_explained(application_id, gap_start, gap_end, correspondence):
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
    correspondence,
    as_of,
    rules,
) -> Dict[str, ElementResult]:
    education_entries = [h for h in history if h.get("entry_type") in ("medical-school", "residency")]
    experience_entries = [h for h in history if h.get("entry_type") in ("employment", "teaching")]
    return {
        "licensure": resolve_licensure(credentials, licence_lookup_wa, licence_lookup_other, as_of),
        "education": resolve_attempt_tracked_element(
            "education", "education-and-training", education_entries, verification_replies, verification_attempts, as_of, rules
        ),
        "experience": resolve_attempt_tracked_element(
            "experience", "affiliation-and-employment", experience_entries, verification_replies, verification_attempts, as_of, rules
        ),
        "certification": resolve_certification(credentials, certification_replies, as_of),
        "references": resolve_references(referees, peer_reference_replies, as_of, rules),
        "gaps": resolve_gaps(application_id, history, correspondence, rules),
    }
