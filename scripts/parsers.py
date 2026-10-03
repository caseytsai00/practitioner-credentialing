from __future__ import annotations

import csv
import os
import re
from typing import Dict, List


def load_csv(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def filter_rows(rows: List[Dict[str, str]], **kwargs: str) -> List[Dict[str, str]]:
    return [row for row in rows if all(row.get(key) == value for key, value in kwargs.items())]


_CSV_FILES = {
    "applications": "applications.csv",
    "disclosures": "application-disclosures.csv",
    "declared_history": "declared-history.csv",
    "declared_credentials": "declared-credentials.csv",
    "privilege_requests": "privilege-requests.csv",
    "licence_lookup_wa": "licence-lookup-wa.csv",
    "licence_lookup_other": "licence-lookup-other-states.csv",
    "certification_replies": "certification-replies.csv",
    "verification_replies": "verification-replies.csv",
    "verification_attempts": "verification-attempts.csv",
    "peer_referees": "peer-referees.csv",
    "peer_reference_replies": "peer-reference-replies.csv",
    "correspondence": "correspondence.csv",
}


_HEADER_FIELD_RE = re.compile(r"\*\*([^:*]+):\*\*\s*(.*)")
_LETTER_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z-]+)_(APP-[\w-]+)\.md$")
_DISPOSITION_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_disposition_(APP-[\w-]+)\.md$")


def _parse_header_fields(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for line in text.splitlines():
        match = _HEADER_FIELD_RE.match(line.strip())
        if match:
            fields[match.group(1).strip()] = match.group(2).strip()
    return fields


def _load_letters(dir_path: str) -> Dict[str, dict]:
    letters: Dict[str, dict] = {}
    if not os.path.isdir(dir_path):
        return letters
    for filename in sorted(os.listdir(dir_path)):
        match = _LETTER_FILENAME_RE.match(filename)
        if not match:
            continue
        with open(os.path.join(dir_path, filename), encoding="utf-8") as f:
            text = f.read()
        letters[filename] = {
            "filename": filename,
            "date": match.group(1),
            "letter_type": match.group(2),
            "application_id": match.group(3),
            "raw_text": text,
        }
    return letters


def _load_decisions(dir_path: str) -> Dict[str, dict]:
    decisions: Dict[str, dict] = {}
    if not os.path.isdir(dir_path):
        return decisions
    for filename in sorted(os.listdir(dir_path)):
        if not filename.endswith(".md"):
            continue
        with open(os.path.join(dir_path, filename), encoding="utf-8") as f:
            text = f.read()
        fields = _parse_header_fields(text)
        decision_id = fields.get("Decision ID")
        if not decision_id:
            continue
        privileges = [p.strip() for p in fields.get("Privileges", "").split(",") if p.strip()]
        decisions[decision_id] = {
            "decision_id": decision_id,
            "body": fields.get("Body", ""),
            "signatory": fields.get("Signatory", ""),
            "role": fields.get("Role", ""),
            "application_id": fields.get("Application", ""),
            "revision": int(fields["Revision"]) if fields.get("Revision") else None,
            "decision_date": fields.get("Decision date", ""),
            "outcome": fields.get("Outcome", ""),
            "privileges": privileges,
            "criteria_version": fields.get("Criteria version", ""),
            "reason": fields.get("Reason") or None,
            "effective_date": fields.get("Effective date") or None,
            "supersedes": fields.get("Supersedes") or None,
            "filename": filename,
            "raw_text": text,
        }
    return decisions


def _load_dispositions(dir_path: str) -> Dict[str, dict]:
    dispositions: Dict[str, dict] = {}
    if not os.path.isdir(dir_path):
        return dispositions
    for filename in sorted(os.listdir(dir_path)):
        match = _DISPOSITION_FILENAME_RE.match(filename)
        if not match:
            continue
        with open(os.path.join(dir_path, filename), encoding="utf-8") as f:
            text = f.read()
        fields = _parse_header_fields(text)
        dispositions[filename] = {
            "filename": filename,
            "date": match.group(1),
            "application_id": match.group(2),
            "recorded_by": fields.get("Recorded by", ""),
            "raw_text": text,
        }
    return dispositions


class BatchData:
    def __init__(self, batch_dir: str) -> None:
        self.batch_dir = batch_dir
        for attr_name, filename in _CSV_FILES.items():
            setattr(self, attr_name, load_csv(os.path.join(batch_dir, filename)))
        self.letters = _load_letters(os.path.join(batch_dir, "letters"))
        self.decisions = _load_decisions(os.path.join(batch_dir, "decisions"))
        self.dispositions = _load_dispositions(os.path.join(batch_dir, "dispositions"))

    def application_ids(self) -> List[str]:
        return sorted({row["application_id"] for row in self.applications})

    def decision_filenames(self) -> List[str]:
        return sorted(d["filename"] for d in self.decisions.values())
