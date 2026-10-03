from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

import jsonschema

from scripts.model import ApplicationRecord


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        digest.update(f.read())
    return digest.hexdigest()


def build_snapshot(
    *,
    batch: int,
    as_of: str,
    predecessor: Optional[Dict[str, str]],
    consumed: Dict[str, List[str]],
    produced: List[str],
    rules_file: str,
    applications: List[ApplicationRecord],
    snapshot_id: str,
) -> Dict[str, Any]:
    return {
        "schema_version": "credentialing-snapshot/1",
        "snapshot_id": snapshot_id,
        "predecessor": predecessor,
        "batch": batch,
        "as_of": as_of,
        "consumed": consumed,
        "produced": produced,
        "rules_file": rules_file,
        "applications": [app.to_dict() for app in applications],
    }


def validate_snapshot(snapshot: Dict[str, Any], schema_path: str) -> None:
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(instance=snapshot, schema=schema)
