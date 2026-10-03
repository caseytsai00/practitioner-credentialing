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

  (Note: after the post-review fix round below, which decision counts as the admitted one for
  `APP-2026-037` changed -- see that section's item 5 -- but the overall count of 25 did not.)

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

## Post-review fixes (independent whole-branch review, 2026-10-03)

After the three batches above were sealed, an independent reviewer (a fresh model instance, with
no access to this session's reasoning, reviewing the full diff and the sealed snapshots read-only)
found 3 Critical and 7 Important issues -- all real, all visible in the sealed output, none
hypothetical. Each was fixed with a regression test confirmed RED before the fix and GREEN after.
Full narrative in `deliverables/run-log.md`'s "Post-review fix round" entry; summary here with
what changed in the sealed data specifically:

1. **A disposition that explicitly declined to clear a finding was read as clearing it.**
   `office-exports/batch-03/dispositions/2026-05-06_disposition_APP-2026-015.md` says the board
   credential "is not full and unrestricted" and "I make no recommendation on the privileges
   themselves" while still routing the file to committee. `parse_disposition_outcome` treated
   "present the file to the committee" alone as a clearing determination, so `APP-2026-015`
   sealed as `licensure: resolved`, `packet_presentable: true` with its own board-action finding
   still open. **Fixed**: that phrase alone no longer clears anything; only an actual
   determination ("no bar to appointment", "sufficient and the file may proceed") does. After the
   fix, `APP-2026-015` correctly stays `in-verification` with `licensure: finding`, and its
   disposition is now flagged as not automatically interpretable (it doesn't match any known
   clearing/discontinue/amend phrasing) -- which correctly flips batch 3's run result from
   `supported` to `partial`. That is the fix working as intended, not a regression: the Skill was
   never supposed to decide this on its own.
2. **A Governing Body decision's own `Conditions:` block was dropped.**
   `office-exports/batch-02/decisions/2026-04-14_GBD-2026-039.md` grants
   `approved-with-conditions` with two dated conditions (a licence re-verification due
   2026-11-30, a Clinical Director concurrence due 2026-06-30) in a `**Conditions:**` bullet
   block the header-field parser couldn't see. `APP-2026-039` sealed as
   `active-with-conditions` with `monitored_conditions: []` -- asserting a status its own payload
   contradicted. **Fixed**: `scripts/parsers.py` now parses that block; `APP-2026-039` now seals
   with both conditions present, each with its real due date.
3. **`activation.privileges` carried a concatenated non-code wherever the office used `; `.**
   Nine real decision documents separate multiple privilege codes with `; ` rather than `,`;
   splitting on `,` alone left six sealed entries (`APP-2026-002`, `APP-2026-014` (batches 2-3),
   `APP-2026-026`, `APP-2026-039` (batches 2-3)) with `["PRIV-HOSP; PRIV-IM"]` -- not a published
   code, unmatchable against `privilege-requests.csv`. **Fixed**: splits on `[;,]`; all six now
   carry correct individual codes (e.g. `["PRIV-HOSP", "PRIV-IM"]`).
4. **A refused decision produced no action-queue item unless it was a revision mismatch.**
   `APP-2026-038` (batch 2, `decision-inadmissible` on `MEC-2026-036`, the Executive Committee
   improperly issuing `approved`) sealed with `action_queue: []`. **Fixed**: every refusal now
   queues an item naming the decision and asking for it to be corrected with the issuing body.
5. **The duplicate-body refusal would have blocked a legitimate follow-up decision.** Real case,
   found once fix 4 made it visible: `APP-2026-037` has two Governing Body decisions for revision
   1 -- `GBD-2026-036` (2026-05-01, grants `PRIV-FM`) and `GBD-2026-037` (2026-05-12, "The
   Governing Body considered the file again", grants `PRIV-FM; PRIV-HOSP`, a later effective date
   of 2026-05-15). Admitting only the first (as a same-body "duplicate" check always did) meant
   the added `PRIV-HOSP` and the corrected effective date were silently dropped. **Fixed**:
   `evaluate_decisions` now treats the chronologically latest decision per body as the candidate
   for admission; the earlier one is refused as superseded by it, not as a duplicate. After the
   fix, `APP-2026-037`'s `approval_decision_id` is `GBD-2026-037`, and its sealed `activation`
   correctly carries both privilege codes and the 2026-05-15 effective date.
6. **A deferred or denied decision's stated reason never reached the action queue.**
   `APP-2026-034` sealed `deferred` in batches 2 and 3 with `action_queue: []`, although
   `GBD-2026-032`'s `Reason` field states exactly what's owed ("one further peer reference from a
   referee outside the applicant's current group practice") and the office's own
   `2026-04-16_deferral-chase_APP-2026-034.md` letter acted on it. **Fixed**: the decision's
   `reason` is now queued whenever a Governing Body decision is admitted as `denied` or
   `deferred-pending-information`.
7. **The 3-attempts/21-days cadence, documented in `rules.md` as covering references, was never
   wired into `resolve_references`.** Real cases `REF-1401`/`APP-2026-014` and
   `REF-2302`/`APP-2026-025` each had attempts logged with no reply, yet sealed with a generic
   "chase" message rather than a "silence is not a pass" escalation. **Fixed**: `resolve_references`
   now reads `verification_attempts` the same way `resolve_attempt_tracked_element` already did.
8. **A `confirmed-with-discrepancy` reply was treated as no reply at all.** `APP-2026-030`'s
   `ENT-3002`/`VR-3002` entry (Mosswater Valley Hospital) is `confirmed-with-discrepancy`; the
   applicant's revision 2 corrected the declared date to match, but `experience` stayed
   `outstanding` forever because only a bare `confirmed` outcome counted as a reply. **Fixed**:
   `confirmed-with-discrepancy` now counts too (the discrepancy itself is handled separately).
9. **A discontinued or withdrawn file lost its own history the batch after.** `APP-2026-029`'s
   "Notify applicant of discontinuance ..." action item was present in batch 2 (when it was
   recorded) and gone in batch 3, because the sticky terminal-state short-circuit defaulted
   `decisions`/`action_queue`/`monitored_conditions` to empty rather than carrying forward what
   was true when the status was set. **Fixed**: these are now persisted in the ledger at the
   moment a file goes terminal and reconstructed on every later batch.
10. **`README.md` documented a `--batch 4` resume that would crash with a raw `KeyError`.**
    `scripts/run_batch.py` only had export dates for batches 1-3 built in. **Fixed**: added a
    `--as-of` override; omitting it for an unknown batch now blocks cleanly with a clear reason
    instead of a traceback.
11. **`--force-resupersede` did no preservation itself**, relying entirely on the operator
    remembering to copy the existing sealed file aside by hand first -- and `SKILL.md` pointed to
    a README section documenting that manual step that didn't actually exist. **Fixed**: the flag
    now copies the existing file to `batch-0N.superseded-<timestamp>.json` automatically before
    overwriting; this fix round's own resupersede (below) is the first time it did so.

All three sealed snapshots were affected by one or more of the above and were regenerated;
the previously-sealed bytes from immediately before this fix round are preserved, byte-for-byte,
at `deliverables/snapshots/batch-0N.superseded-<timestamp>.json` for each batch (now produced
automatically by fix 11, rather than by hand as in the three earlier fix rounds).

**Declined to fix, with reasoning (the reviewer's own severity label was advice; this is the
actual ruling):** the reviewer additionally raised that `tests/test_e2e_batch_0{1,2,3}.py` write
to the real `deliverables/` tree on every `pytest` run, which is not a bug -- it is the explicit
design from the original implementation plan (Tasks 15-17: "This test both verifies behavior AND
performs the actual first real run the assignment requires"), and reflects a real property of the
system: `run-log.md` is a genuine audit trail of every time the CLI actually ran, including from
test invocations, and an idempotent re-run correctly logs itself as unchanged rather than lying
about it. Left as designed. Everything else the reviewer raised as Minor (PPQ findings attaching
to `licensure` rather than a dedicated element; two remaining numeric literals in `engine.py`
outside `rules.md`'s scope; leap-day date arithmetic; `resolve_licensure`/`resolve_certification`
returning on the first problem credential rather than aggregating; `consumed.record_files` listing
every CSV rather than only ones with matching rows; an attempt-count message that can undercount
real attempts; the `routed-to-clinical-director` element state never being emitted; use of
`datetime.utcnow()`) is left as a known limitation rather than fixed, consistent with fixing only
Critical and Important findings in this pass.
