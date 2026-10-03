from __future__ import annotations

import csv
import os
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


class BatchData:
    def __init__(self, batch_dir: str) -> None:
        self.batch_dir = batch_dir
        for attr_name, filename in _CSV_FILES.items():
            setattr(self, attr_name, load_csv(os.path.join(batch_dir, filename)))

    def application_ids(self) -> List[str]:
        return sorted({row["application_id"] for row in self.applications})
