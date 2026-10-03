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
