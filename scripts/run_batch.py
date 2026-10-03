from __future__ import annotations

import os
import sys

# Make `python3 scripts/run_batch.py` work as documented: running the file directly only puts
# scripts/ itself on sys.path, not the repo root, so the `from scripts.X import ...` imports below
# would fail with ModuleNotFoundError without this. `python3 -m scripts.run_batch` doesn't need it
# (the repo root is already on sys.path in that form), so this is a no-op there.
_REPO_ROOT_FOR_IMPORT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT_FOR_IMPORT not in sys.path:
    sys.path.insert(0, _REPO_ROOT_FOR_IMPORT)

import argparse
import datetime
import json
import traceback
from typing import List, Optional

from scripts.engine import process_batch
from scripts.parsers import BatchData
from scripts.rules import load_rules
from scripts.snapshot import build_snapshot, file_sha256, validate_snapshot
from scripts.state import load_ledger, new_ledger, save_ledger

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF_BY_BATCH = {1: "2026-03-16", 2: "2026-04-20", 3: "2026-05-18"}


def _json_dumps(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True)


def append_run_log(path, command, batch, started_at, consumed, produced, failures, result, note=None):
    finished_at = datetime.datetime.utcnow().isoformat() + "Z"
    lines = [
        "## {} -- batch {} -- {}".format(started_at, batch, result),
        "",
        "- Command: `{}`".format(command),
        "- Started: {}".format(started_at),
        "- Finished: {}".format(finished_at),
        "- Consumed record files: {}".format(", ".join(consumed.get("record_files", [])) or "(none)"),
        "- Consumed documents: {}".format(", ".join(consumed.get("documents", [])) or "(none)"),
        "- Produced: {}".format(", ".join(produced) or "(none)"),
    ]
    if failures:
        lines.append("- Failures:")
        for failure in failures:
            lines.append("  - {}".format(failure))
    else:
        lines.append("- Failures: none")
    if note:
        lines.append("- Note: {}".format(note))
    lines.append("")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Run log\n\nOne entry per invocation of `scripts/run_batch.py`, newest last.\n\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--state", default=None)
    parser.add_argument("--force-resupersede", action="store_true")
    args = parser.parse_args(argv)

    batch_dir = os.path.join(REPO_ROOT, "office-exports", "batch-{:02d}".format(args.batch))
    snapshot_path = os.path.join(REPO_ROOT, "deliverables", "snapshots", "batch-{:02d}.json".format(args.batch))
    state_path = os.path.join(REPO_ROOT, "deliverables", "state", "batch-{:02d}.state.json".format(args.batch))
    rules_path = os.path.join(REPO_ROOT, "deliverables", "rules.md")
    run_log_path = os.path.join(REPO_ROOT, "deliverables", "run-log.md")
    schema_path = os.path.join(REPO_ROOT, "snapshot.schema.json")

    command = "python3 scripts/run_batch.py --batch {}".format(args.batch)
    if args.state:
        command += " --state {}".format(os.path.relpath(args.state, REPO_ROOT))
    started_at = datetime.datetime.utcnow().isoformat() + "Z"

    try:
        rules = load_rules(rules_path)
        ledger = load_ledger(args.state) if args.state else new_ledger()
        batch = BatchData(batch_dir)
        as_of = AS_OF_BY_BATCH[args.batch]

        records, updated_ledger, warnings = process_batch(batch, ledger, rules, as_of)

        if args.batch == 1:
            predecessor = None
        else:
            prior_path = os.path.join(
                REPO_ROOT, "deliverables", "snapshots", "batch-{:02d}.json".format(args.batch - 1)
            )
            predecessor = {"path": os.path.relpath(prior_path, REPO_ROOT), "sha256": file_sha256(prior_path)}

        consumed = {
            "record_files": sorted(f for f in os.listdir(batch_dir) if f.endswith(".csv")),
            "documents": sorted(
                list(batch.letters.keys()) + batch.decision_filenames() + list(batch.dispositions.keys())
            ),
        }
        produced = [
            os.path.relpath(snapshot_path, REPO_ROOT),
            os.path.relpath(state_path, REPO_ROOT),
            os.path.relpath(run_log_path, REPO_ROOT),
        ]
        snapshot = build_snapshot(
            batch=args.batch,
            as_of=as_of,
            predecessor=predecessor,
            consumed=consumed,
            produced=produced,
            rules_file=os.path.relpath(rules_path, REPO_ROOT),
            applications=records,
            snapshot_id="batch-{:02d}-{}".format(
                args.batch, datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
            ),
        )
        validate_snapshot(snapshot, schema_path)

        result = "supported" if not warnings else "partial"

        if os.path.exists(snapshot_path) and not args.force_resupersede:
            with open(snapshot_path, encoding="utf-8") as f:
                existing = json.load(f)
            existing_comparable = dict(existing)
            existing_comparable.pop("snapshot_id", None)
            new_comparable = dict(snapshot)
            new_comparable.pop("snapshot_id", None)
            if existing_comparable == new_comparable:
                append_run_log(
                    run_log_path, command, args.batch, started_at, consumed, produced, warnings, result,
                    note="unchanged re-run; sealed snapshot left untouched",
                )
                return 0
            raise RuntimeError(
                "batch {} already has a sealed snapshot that differs from this run's result; "
                "rerun with --force-resupersede to regenerate it and every later snapshot".format(args.batch)
            )

        os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(_json_dumps(snapshot))
            f.write("\n")
        save_ledger(updated_ledger, state_path)

        append_run_log(run_log_path, command, args.batch, started_at, consumed, produced, warnings, result)
        return 0
    except Exception as exc:  # noqa: BLE001 -- a blocked run must still log and exit cleanly
        append_run_log(
            run_log_path,
            command,
            args.batch,
            started_at,
            {"record_files": [], "documents": []},
            [],
            [str(exc)],
            "blocked",
            note=traceback.format_exc(),
        )
        print("BLOCKED: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
