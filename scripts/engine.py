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
        # "confirmed-with-discrepancy" means the source DID reply -- the discrepancy itself is
        # handled separately (detect_discrepancies / the applicant resolving it in writing or by
        # amendment), so treating only a bare "confirmed" as a reply leaves an otherwise-settled
        # entry permanently "outstanding" even after the applicant corrects the value (real case:
        # VR-3002/APP-2026-030).
        confirmed = any(
            r.get("entry_id") == entry_id
            and r.get("element") == element_label
            and r.get("outcome") in ("confirmed", "confirmed-with-discrepancy")
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


def resolve_references(referees, peer_reference_replies, verification_attempts, as_of, rules) -> ElementResult:
    required = rules["references.required_count"]
    staleness_years = rules["references.staleness_years"]
    max_attempts = rules["verification.attempt_max_count"]
    min_spacing = rules["verification.attempt_min_spacing_days"]
    as_of_date = _parse_date(as_of)
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
        "references": resolve_references(referees, peer_reference_replies, verification_attempts, as_of, rules),
        "gaps": resolve_gaps(application_id, history, correspondence, rules),
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


def detect_eligibility_mismatch(priv_requests, history, credentials) -> bool:
    if not priv_requests:
        return False
    supported_terms = set()
    for entry in history:
        if entry.get("entry_type") in ("residency", "medical-school", "employment", "teaching"):
            supported_terms.add((entry.get("role") or "").lower())
            supported_terms.add((entry.get("organization") or "").lower())
    for cred in credentials:
        supported_terms.add((cred.get("issuer") or "").lower())

    for request in priv_requests:
        name = (request.get("privilege_name") or "").lower()
        tokens = [token for token in name.replace(",", " ").split() if len(token) > 3]
        if not tokens:
            continue
        if not any(any(token in supported for supported in supported_terms) for token in tokens):
            return True
    return False


def detect_ppq_findings(disclosures) -> bool:
    return any(d.get("answer") == "Yes" for d in disclosures)


_VALID_OUTCOMES_BY_BODY = {
    "Executive Committee of the Medical Staff": {"recommended"},
    "Governing Body": {"approved", "approved-with-conditions", "deferred-pending-information", "denied"},
}


def admit_decision(decision: dict, already_admitted_bodies=None):
    already_admitted_bodies = already_admitted_bodies or set()
    body = decision.get("body", "")
    outcome = decision.get("outcome", "")

    valid_outcomes = _VALID_OUTCOMES_BY_BODY.get(body)
    if valid_outcomes is None:
        return False, "issuing body '{}' is not recognized".format(body)
    if outcome not in valid_outcomes:
        return False, "{} may not issue outcome '{}'".format(body, outcome)
    if not decision.get("signatory"):
        return False, "decision carries no named signatory"
    if not decision.get("role"):
        return False, "decision carries no signatory role"
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


def apply_dispositions(elements, dispositions):
    elements = dict(elements)
    status_override = None
    action_items = []
    unmatched = False
    for disposition in sorted(dispositions, key=lambda d: d["date"]):
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
        correspondence=store.get("correspondence", []),
        as_of=as_of,
        rules=rules,
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
            elements["education"] = "discrepancy"
        if touched_types & {"employment", "teaching"}:
            elements["experience"] = "discrepancy"
        for d in discrepancies:
            action_queue.append(
                ActionItem(
                    item="Discrepancy on {}: declared {} is {}, source says {}; applicant must resolve in writing or amend".format(
                        d["entry_id"], d["field"], d["declared"], d["verified"]
                    ),
                    owner="Applicant",
                )
            )

    if detect_eligibility_mismatch(
        store.get("privilege_requests", []), store.get("declared_history", []), store.get("declared_credentials", [])
    ):
        elements["certification"] = "eligibility-question"
        action_queue.append(
            ActionItem(
                item="Nothing on file supports the privilege requested; Clinical Director review needed",
                owner="Clinical Director",
            )
        )

    if detect_ppq_findings(store.get("disclosures", [])):
        elements["licensure"] = "finding"
        action_queue.append(
            ActionItem(
                item="A professional practice question was answered Yes; Clinical Director must judge whether this finding is disqualifying",
                owner="Clinical Director",
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
