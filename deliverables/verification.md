# Verification

This document is the Skill-builder's own check of the sealed snapshots against the office's raw
records, using a method other than the Skill's own engine code.

## Method

`scripts/recount_check.py` reads the raw CSV and decision-document files directly with plain
`csv`/regex parsing -- it does not import `scripts.engine` or `scripts.parsers` -- and recomputes
two figures independently of the Skill's own computation path:

1. Which applications have at least one professional-practice-question answered "Yes" in a given
   batch's raw `application-disclosures.csv` (a finding trigger the engine is supposed to route
   to the Clinical Director, never auto-resolve).
2. How many decision documents in a batch's `decisions/` folder structurally look like an
   admitted Governing Body approval (`Body: Governing Body`, `Outcome: approved` or
   `approved-with-conditions`) -- an upper bound on how many approvals the engine's admission
   check should end up admitting (it can admit fewer, e.g. on a duplicate or a revision that no
   longer matches, but never more).

## What was checked and what was found

- **PPQ "Yes" findings, batch 1.** `count_ppq_yes_findings('office-exports/batch-01')` returned
  `{'APP-2026-032': 1}`. Cross-checking `deliverables/snapshots/batch-01.json`, this surfaced a
  real gap: the design spec called for any PPQ answered "Yes" to force a `finding`, routed to the
  Clinical Director, but `scripts/engine.py` never actually implemented that trigger. Before the
  fix, APP-2026-032's `licensure` element read `resolved` in batch 1 -- not because anyone judged
  the finding, but because nothing in the code ever flagged it, and the other five elements
  happened to resolve on their own evidence. **Fixed**: added `detect_ppq_findings` and wired it
  into `process_application` (`scripts/engine.py`), overriding `licensure` to `finding` and
  queuing a Clinical Director action item whenever any disclosure is answered "Yes". After the
  fix, batch 1 correctly shows APP-2026-032's `licensure` as `finding` with that action item;
  batch 2 shows it `resolved` once the real disposition
  (`office-exports/batch-02/dispositions/2026-04-02_disposition_APP-2026-032.md`, "I record no
  bar to appointment and no condition") clears it. One residual rough edge found while writing
  this up and left as a documented limitation rather than a fourth fix cycle: the Clinical
  Director action item this override queues stays in `action_queue` even after the element is
  later resolved by a clearing disposition, since it is appended unconditionally before
  dispositions are applied. It is a stale, redundant informational entry once resolved, not a
  wrong element state or status -- see "Known limitations" in `deliverables/rules.md`, where this
  is now also recorded.
- **Admitted-shape Governing Body approvals, batch 2.** `count_admitted_gb_approvals(...)`
  returned 8 structurally-approval-shaped decision documents in
  `office-exports/batch-02/decisions/`. The batch-02 snapshot shows 7 applications with a
  non-null `approval_decision_id` -- a real gap, not a benign rounding difference. Tracing it
  found a second genuine bug: `evaluate_decisions` filtered out any decision whose `revision`
  field didn't match the application's *current* revision before building `decision_records` at
  all, so the decision didn't just get refused -- it vanished from `decisions[]` entirely, with no
  `admitted: false` and no reason, violating the snapshot schema's own rule that a refused record
  stays in every later snapshot with its reason. The specific case:
  `GBD-2026-034` approved `APP-2026-036` at revision 1, but an unrelated correction (an employer
  name fix) bumped the file to revision 2 later in the same batch, so the decision's revision no
  longer matched. **Fixed**: `evaluate_decisions` now keeps every decision for the application in
  `decision_records`; one naming a superseded revision is refused with an explicit reason
  (`"decision names revision 1; the file is now at revision 2"`) and queues a Medical Services
  Professional action item asking whether it still applies. After the fix, APP-2026-036's
  `decisions[]` in batch 2 correctly shows both its Executive Committee and Governing Body
  decisions as `admitted: false` with that reason, and its `approval_decision_id` is `null`. The
  remaining 7-of-8 count is now fully accounted for and correctly reasoned, not just numerically
  matched.
- **Final tally, batch 3.** Across batches 2 and 3 combined, `count_admitted_gb_approvals`
  finds 8 + 19 = 27 structurally-approval-shaped Governing Body decisions, but
  `deliverables/snapshots/batch-03.json` shows 25 applications with a non-null
  `approval_decision_id`. Both of the 2 that don't carry through were spot-checked by hand and
  are correctly refused, each for a distinct, visible reason in its `decisions[]` entry:
  - `APP-2026-036`'s original `GBD-2026-034` (revision 1) stays refused for the revision mismatch
    above; a *new* Governing Body decision, `GBD-2026-035`, was admitted for revision 2 in batch 3
    and correctly supplies `approval_decision_id`.
  - `APP-2026-037` already had an admitted Governing Body decision (`GBD-2026-036`, batch 2) for
    revision 1; a second one (`GBD-2026-037`, batch 3) for the same application and revision is
    refused with reason `"a decision from Governing Body is already admitted for this application
    and revision"` -- the duplicate-admission check working as designed.

  Every one of the 25 admitted approvals was spot-checked by hand against its `decisions[]` entry
  to confirm the `admitted: true` decision really is a `Governing Body`
  `approved`/`approved-with-conditions` record, per the admission rule in `deliverables/rules.md`.
- **Schema validation.** `python3 -m pytest tests/test_e2e_batch_01.py tests/test_e2e_batch_02.py tests/test_e2e_batch_03.py -v`
  passes, which validates every sealed snapshot against `snapshot.schema.json` as part of
  `scripts.snapshot.validate_snapshot` running inside `scripts.run_batch.main`.

## What changed as a result

Three real bugs were found and fixed during this verification pass, each with a regression test
confirmed RED before the fix and GREEN after, and each requiring the sealed batch snapshots it
affected to be regenerated and superseded per the assignment's rule 6 (superseded bytes preserved
under `deliverables/snapshots/batch-0N.superseded-<reason>.json`; full narrative for each in
`deliverables/run-log.md`'s "Supersede note" entries):

1. `compute_status` checked "are all six elements resolved" before checking for an admitted
   Governing Body outcome, so an already-approved file could read `in-verification` forever if
   this engine's own element tracking still had an unaddressed `finding`. Fixed in
   `scripts/engine.py:compute_status`. Affected batches 2 and 3.
2. `evaluate_decisions` silently dropped any decision whose revision no longer matched the
   application's current revision, instead of refusing it with a reason. Fixed in
   `scripts/engine.py:evaluate_decisions`. Affected batches 2 and 3.
3. The design spec's "PPQ answered Yes -> finding" rule was never implemented. Added
   `detect_ppq_findings` and wired it into `scripts/engine.py:process_application`. Affected all
   three batches (APP-2026-032 first appears in batch 1).

One minor, deliberately unfixed rough edge is documented above and in `deliverables/rules.md`'s
"Known limitations": a Clinical-Director action item queued by the PPQ-finding override can
linger in `action_queue` after the element it concerns is later resolved by a disposition.
