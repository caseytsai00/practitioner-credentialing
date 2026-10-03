# Practitioner credentialing

Build a reusable Agent Skill that runs a medical staff office's initial-appointment credentialing file from application intake to recorded appointment and active privileges.

## Start

1. Read the [full task](https://docs.google.com/document/d/1HhmU8Jay09XHDci38hl9ZOX_dMryaSv4aFLCPu1Nk-E/edit): it owns the scope, deliverables and acceptance requirements.
2. Create your own repository from [this starter](https://github.com/GitRollTraining/practitioner-credentialing) using **Use this template → Create a new repository**, then clone your copy and work there.

## Supplied files

| File | Purpose |
|---|---|
| `README.md` | Starting instructions and the full-task link. |
| `snapshot.schema.json` | The required shape of the per-batch snapshot your Skill writes. Validate every snapshot against it. Your implementation language and validation library are yours. |

You create the Skill, its implementation, your own checks and every output the task requires. Nothing here implements any part of the office's work.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.7+ (tested on 3.7.4). Dependencies: `jsonschema`, `pyyaml`, `pytest` (pinned in
`requirements.txt`).

## Running a batch

```bash
# Batch 1 -- first run, no prior state
python3 scripts/run_batch.py --batch 1

# Batch 2 -- resumes from batch 1's state
python3 scripts/run_batch.py --batch 2 --state deliverables/state/batch-01.state.json

# Batch 3 -- resumes from batch 2's state
python3 scripts/run_batch.py --batch 3 --state deliverables/state/batch-02.state.json
```

Each command is idempotent: running the same batch again with the same inputs leaves the already
sealed `deliverables/snapshots/batch-0N.json` byte-for-byte unchanged (only `run-log.md` gets a
new entry). To resume work on a batch the office releases later (a hypothetical batch 4), run
`python3 scripts/run_batch.py --batch 4 --state deliverables/state/batch-03.state.json` once
`office-exports/batch-04/` exists.

## What supported / partial / blocked / deferred look like in this repo

- **Supported**: `run-log.md`'s entry for that batch says `supported`; the sealed snapshot's
  `applications[]` covers every file in the caseload.
- **Partial**: the entry says `partial`; the affected applications' `action_queue` includes an
  item like "...could not be automatically interpreted", naming who must read it by hand.
- **Blocked**: the entry says `blocked` with the error and affected scope; no snapshot file for
  that batch exists or changed, and the prior batch's sealed snapshot is exactly as it was.
- **Deferred**: not a run outcome at all -- look at `applications[].status` inside a snapshot.
  `"deferred"`, `"denied"`, `"discontinued"`, and `"withdrawn"` are correct, complete results for
  that one file; the run itself is still `supported`.

## Verifying the outputs

1. Every sealed snapshot validates against `snapshot.schema.json` (the test suite enforces this
   on every run; to check by hand: `python3 -c "import json, jsonschema; jsonschema.validate(json.load(open('deliverables/snapshots/batch-01.json')), json.load(open('snapshot.schema.json')))"`).
2. `deliverables/verification.md` documents an independent recount of at least one figure per
   batch, by a method other than this Skill's own code.
3. `python3 -m pytest -v` runs the full test suite, including the three real end-to-end batch
   runs.

## Resuming work someone else left

1. Read `deliverables/run-log.md`'s last entry to see which batch was last run and what state file
   it produced.
2. Confirm `office-exports/batch-0(N+1)/` exists (the office's next closed export).
3. Run `python3 scripts/run_batch.py --batch N+1 --state deliverables/state/batch-0N.state.json`.
4. Read the new snapshot's `applications[].action_queue` entries and the new `run-log.md` entry
   for anything that needs a human (the Medical Services Professional, Clinical Director,
   Executive Committee, Governing Body, or the applicant) before the next run.

## Before you work

**Interview rule.** You conduct the stakeholder interview yourself, and the questions are yours. Do not connect a coding agent or any other AI to the interview to run, script, or automate it. The interview transcript is assessed together with the code; a project whose interview was run by an agent is not scored.

- Export your interview as the original Work Sim Markdown, save one final complete file per session under `interviews/`, and commit and push it with your code. Do not rewrite the export. If the export is unavailable, contact the facilitator.
- No runtime is supplied. Choose the dependencies your Skill needs and document how to install and run it.
- Complete the program's coding-session capture setup in the course before assessed work, and confirm your session is being captured after your first meaningful commit. Ask the facilitator to repair missing capture before you continue.
- Meet the stakeholder to obtain the relevant business source links and context; the facilitator supplies the interview link with the assignment. Read those online sources through the intended access route.
