---
name: practitioner-credentialing
description: Runs one closed export batch of Larkhollow Community Hospital's initial-appointment credentialing caseload forward -- intake completeness, the six verification elements, discrepancies, Clinical Director dispositions, committee/Governing Body decisions, and activation -- producing the next sealed snapshot and a human action queue. Use when asked to process, advance, or resume a practitioner-credentialing batch.
---

# Practitioner credentialing Skill

## What this Skill does

Given one of the office's closed export batches (`office-exports/batch-0N/`) and the state the
previous run left behind, this Skill computes, for every application file in the caseload as of
that batch's export date: its status, the state of each of its six verified elements
(licensure, experience, gaps, education, certification, references), whether its packet is
presentable, every decision record received with admitted/refused and why, its activation if
approved, any monitored conditions, and a human action queue naming what is still owed and by
whom. It seals the result as a snapshot conforming to `snapshot.schema.json` and writes its own
continuity state for the next run.

## Human authority this Skill must never cross

Five judgments are never computed by this Skill, regardless of what the data shows:

1. Whether a gap explanation is satisfactory.
2. Whether a finding is disqualifying.
3. Whether to discontinue an application on eligibility grounds.
4. Whether to recommend appointment and which privileges.
5. Whether to grant, modify, defer, or deny.

Each only ever appears as an action-queue entry naming its owner (the Clinical Director, the
Executive Committee, the Governing Body, or the Medical Services Professional). The Skill
consumes the resulting human record -- a Clinical Director disposition document or a committee/
Governing Body decision record -- once one exists, and never before. See
`deliverables/rules.md` for the exact areas this covers and where that boundary comes from.

## Inputs

- A batch number (1, 2, or 3), resolved to `office-exports/batch-0N/` in this repository.
- Optionally, the prior run's state file (`deliverables/state/batch-0(N-1).state.json`). Omit it
  only for batch 1.

No case-specific threshold is hardcoded in this Skill's code. Every number it applies --
the 30-day clocks, the 3-attempts/21-days verification cadence, the 2 required peer referees, the
2-year reference staleness window, the 2-year appointment cycle -- is read at runtime from
`deliverables/rules.md`, which also states, for each one, whether it came from the stakeholder
interview or was a session decision by the project owner (never silently invented).

## Invoking it

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

# Batch 1 -- no prior state
python3 scripts/run_batch.py --batch 1

# Batch 2 -- resumes from batch 1's state
python3 scripts/run_batch.py --batch 2 --state deliverables/state/batch-01.state.json

# Batch 3 -- resumes from batch 2's state
python3 scripts/run_batch.py --batch 3 --state deliverables/state/batch-02.state.json
```

Each invocation writes (or refreshes) exactly three files: `deliverables/snapshots/batch-0N.json`,
`deliverables/state/batch-0N.state.json`, and an appended entry in `deliverables/run-log.md`.

## Outputs

- `deliverables/snapshots/batch-0N.json` -- the sealed, schema-validated snapshot. The human
  action queue lives inside it, per application, in `applications[].action_queue`.
- `deliverables/state/batch-0N.state.json` -- this Skill's own continuity ledger for the next run.
  Not schema-governed; an implementation detail, not a deliverable to hand-inspect.
- An appended entry in `deliverables/run-log.md` naming the command, what was consumed and
  produced, and every failure with its affected scope.

## Behaviour on failure and on re-run

- A run that fully completes but leaves some applications or records unsettled (e.g. a Clinical
  Director disposition whose wording the Skill can't confidently interpret) is **partial**: the
  snapshot is still sealed, those files carry what's outstanding in their `action_queue`, and
  `run-log.md` names the affected scope and reason.
- A run that cannot even read its batch (a missing/corrupt input file, a schema-validation
  failure) is **blocked**: it writes nothing to `deliverables/snapshots/` or
  `deliverables/state/` for that batch, the previously sealed snapshot stands untouched, and
  `run-log.md` records the attempt, the error, and the affected scope. Exit code `1`.
- Re-running a batch whose result is unchanged leaves the already-sealed snapshot's bytes
  untouched (only the run log gets a new entry). Re-running a batch whose result actually
  changed (e.g. a genuine bug fix) refuses by default -- pass `--force-resupersede` to regenerate
  it under a new `snapshot_id`. The flag itself automatically preserves the prior sealed bytes
  unchanged at `batch-0N.superseded-<timestamp>.json` before overwriting, and `run-log.md`
  records which file superseded which. Only `batch-0N.json` itself needs regenerating this way
  for *that* batch -- re-run every later batch normally afterward so its ledger carries the
  correction forward.
- `deferred`/`denied`/`discontinued`/`withdrawn` are correct, complete results of a run, not
  failures -- they represent a business hold or outcome, not something gone wrong with the Skill.

## Code and references

- `scripts/run_batch.py` -- the entrypoint described above.
- `scripts/parsers.py` -- reads one batch folder's CSVs and markdown documents.
- `scripts/rules.py` -- loads every threshold from `deliverables/rules.md`.
- `scripts/engine.py` -- the state machine: intake, the six elements, discrepancies, eligibility
  mismatches, disposition consumption, decision admission, activation, terminal states.
- `scripts/state.py` -- the continuity ledger.
- `scripts/snapshot.py` -- builds and schema-validates the sealed snapshot.
- `scripts/model.py` -- the output data shapes.
- `deliverables/rules.md` -- every rule this Skill applies, with its exact source.
- `docs/superpowers/specs/2026-10-02-practitioner-credentialing-skill-design.md` -- the full
  design spec this Skill implements.
