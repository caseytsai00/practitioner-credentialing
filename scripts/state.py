from __future__ import annotations

import json
from typing import Any, Dict, Optional

LEDGER_SCHEMA_VERSION = "credentialing-ledger/1"


def new_ledger() -> Dict[str, Any]:
    return {"schema_version": LEDGER_SCHEMA_VERSION, "applications": {}}


def load_ledger(path: Optional[str]) -> Dict[str, Any]:
    if path is None:
        return new_ledger()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_ledger(ledger: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, sort_keys=True)
        f.write("\n")


def get_application_entry(ledger: Dict[str, Any], application_id: str) -> Dict[str, Any]:
    return ledger["applications"].setdefault(
        application_id,
        {
            "revision": 0,
            "elements": {},
            "element_evidence": {},
            "decisions_seen": [],
            "documents_seen": [],
            "status": None,
            "approval_decision_id": None,
            "activation": None,
            "monitored_conditions": [],
            "revision_data": {},
            "last_application_row": None,
        },
    )
