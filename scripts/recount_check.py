from __future__ import annotations

import csv
import os
import re
from typing import Dict

_BODY_RE = re.compile(r"\*\*Body:\*\*\s*(.+)")
_OUTCOME_RE = re.compile(r"\*\*Outcome:\*\*\s*(.+)")


def count_ppq_yes_findings(batch_dir: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    path = os.path.join(batch_dir, "application-disclosures.csv")
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("answer") == "Yes":
                app_id = row["application_id"]
                counts[app_id] = counts.get(app_id, 0) + 1
    return counts


def count_admitted_gb_approvals(decisions_dir: str) -> int:
    if not os.path.isdir(decisions_dir):
        return 0
    total = 0
    for filename in os.listdir(decisions_dir):
        if not filename.endswith(".md"):
            continue
        with open(os.path.join(decisions_dir, filename), encoding="utf-8") as f:
            text = f.read()
        body_match = _BODY_RE.search(text)
        outcome_match = _OUTCOME_RE.search(text)
        body = body_match.group(1).strip() if body_match else ""
        outcome = outcome_match.group(1).strip() if outcome_match else ""
        if body == "Governing Body" and outcome in ("approved", "approved-with-conditions"):
            total += 1
    return total
