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

## Redo audit, 2026-10-03/04 -- rule-sourcing review before a second committee pass

Following a low "Direction" score on the first submission (proposals accepted without checking
them against the office's actual rules), the project owner asked for an audit of 8 named edge
cases against `deliverables/rules.md`/the interview/the task brief and the code, treating the 97
passing tests as evidence of nothing on their own. Full findings list given in chat; fixes made
one edge case at a time, each with its own test written and confirmed failing before the fix,
per the project owner's explicit instruction. This section covers the fixes made so far (code and
tests only -- **no batch has been resealed yet**; resealing is deliberately deferred until every
fix in this round is in, per the project owner's instruction not to reseal more than once).

**Fix round 1 -- accepted-source handling (`scripts/engine.py:resolve_attempt_tracked_element`,
`resolve_certification`).** Two real, previously-unflagged bugs, both found by tracing the
engine's actual behavior against real `office-exports/` rows rather than trusting the existing
tests:

1. `APP-2026-036`/`ENT-3602`: a revision changed the declared employer from "Willowmere Health
   Cooperative" to "Silverbeck Physicians Group" (practice acquisition); the only reply on file at
   that point still confirmed the pre-acquisition name, and the engine read this as `resolved`
   regardless. Confirmed wrong in the already-sealed `batch-02.json`.
2. `APP-2026-022`/`ENT-2201`: the only reply on file for a declared residency came from "Cascade
   Valley Physicians Society" (a state medical society, not the residency program, not a
   designated-equivalent source) while the actual program never responded across 3 logged
   attempts. Silently read as `resolved` in all three sealed snapshots.

First fix pass used organization-name matching alone, which caught both of the above but also
produced a false positive the project owner caught by independently reading the office's actual
accepted-source document, "Accepted sources by element — who may attest" (LARK-ATT-2026.1, now on
file at `docs/office-documents/LARK-ATT-2026.1-accepted-sources.md`, in force from 2026-01-01, not
previously available): `APP-2026-021`/`ENT-2100`'s medical school closed in 2019; the designated
equivalent (FCVS) reported no record; a secondary-source reply from the applicant's current
employer, stating how it obtained its own verification, is exactly what the table calls
admissible "only on impossibility" -- name-matching alone rejected it. Independent confirmation
this rejection was wrong: `APP-2026-021` reaches an admitted Governing Body approval and `active`
status by batch 3 with no discrepancy letter ever issued for it.

Reworked per the real document: education and certification now classify a reply as primary
(matches the declared school/board), designated-equivalent (a named list: ECFMG/FCVS/AMA
Profile/AOA Profile/National Student Clearinghouse for education; ABMS/CertiFACTS/AMA Profile/AOA
Profile/ABPS/ANCC/NCCPA for certification), secondary-only-on-impossibility (education only: the
applicant's most recent affiliation, with a stated reason, and on-file evidence -- a `no-record`
reply or an `undeliverable` attempt -- that the primary/designated-equivalent route is actually
impossible, not merely unanswered), or inadmissible. Affiliations/employment keeps simple
org-name matching against the currently-declared employer, confirmed correct for that element
specifically (the entity being verified for an employment entry *is* the employer, unlike the
other three elements' closed third-party source lists). Licensure left uncoded: neither
`licence-lookup-wa.csv` nor `licence-lookup-other-states.csv` contains a row that isn't already
primary-source in all three batches, so there's nothing in the data's shape to validate a check
against yet.

Re-validated against **every** row in all three batches, not just the ones already known about,
checking for both false positives and false negatives: 81 education replies (78 primary, 1
designated-equivalent, 1 secondary, 1 inadmissible), 40 certification replies (all primary). No
other anomaly anywhere. Tests: `tests/test_engine_elements.py`,
`tests/test_engine_real_data_regressions.py` (drives the real `office-exports/` data directly
through `scripts.engine.process_batch` without touching `deliverables/`, so it can prove a fix
against real data before resealing).

**Fix round 2 -- certification expiry aging and discrepancy-check scope
(`scripts/engine.py:resolve_certification`, `detect_credential_discrepancies`).**
`resolve_certification` never compared a reply's `expiry_date` to `as_of` the way
`resolve_licensure` already compared its own -- a certification could silently outlive the
evidence on file, exactly the "a file sits ready for the committee for weeks while a licence
expires underneath it" scenario the interview opens with. Fixed: reverts to `outstanding` (not
`finding`) once expired. No real case in the office's three batches currently has an expired
certification on file, so this does not change any batch's sealed output -- implemented because
the interview's rule requires it, not because a batch exercises it.

Separately, `detect_discrepancies` only ever compared `declared_history` dates against
`verification_replies` -- `declared_credentials` (licence/certification) were never compared
against their own independent sources at all, despite the interview's reconciliation rule being
general ("the information declared on the application... against... all completed
verifications... any discrepancy"). Added `detect_credential_discrepancies`, scoped to
`declared_issue_date` only, after a real-data check caught a second false positive before it
shipped: an initial, broader version also comparing `declared_expiry_date` flagged
`APP-2026-040`'s WA licence (`MD60096330`) as a discrepancy in batch 3, because the licence
genuinely renewed between batch 2 and batch 3 (`expirationdate` moved from `2026-04-10` to
`2028-04-30`; `firstissuedate` stayed fixed at `2011-06-27`). An expiry date is a live,
forward-moving fact the board's own record keeps current; comparing it against the application's
frozen intake-time snapshot would flag every routine renewal as a false discrepancy demanding
applicant explanation. Narrowed to `declared_issue_date` (a fixed historical fact that never
moves) before implementing; re-ran all three batches before and after narrowing and confirmed the
`APP-2026-040` false positive was the only thing that changed either way. Also deliberately
excludes `declared_status`: the application form and the board use different vocabularies for the
same fact (38 of 40 real certification replies declare "Board certified" against a reply of
"Active"); the one genuine status disagreement in the data, `APP-2026-027`, is already correctly
handled as a `finding` by `resolve_certification`'s own status check, matching how the office's
own letter frames it (a threshold eligibility question for the Clinical Director, not something
the applicant resolves in writing). Documented in full, including the two deliberate exclusions
and why, in `deliverables/rules.md`'s "Reconciliation discrepancy handling" and "Certification
expiry aging" entries.

Re-ran the full engine across all three batches before and after both fix rounds and diffed every
application's `licensure`/`certification` element against the currently-sealed snapshots: zero
unexpected changes either time (the `APP-2026-040` false positive, caught and corrected before
being counted as a "real" diff, is the only thing fix round 2 ever showed). Tests:
`tests/test_engine_discrepancy_eligibility.py`, `tests/test_engine_elements.py`.

**Fix round 3 -- element-state overwrite precedence and the intake criteria-version check
(`scripts/engine.py:process_application`, `missing_intake_items`).**

`detect_eligibility_mismatch` unconditionally overwrote `elements["certification"]` the moment it
fired, with no regard for whatever `resolve_certification` (or a credential discrepancy, fix round
2) had already found there. Real-shaped risk: a certification `resolve_certification` already
flagged `finding` (an inactive board status, exactly `APP-2026-027`'s real shape) on a file whose
privilege request also happens to be unsupported (exactly `APP-2026-029`'s real shape) would have
silently lost the `finding` from the sealed `elements` dict the moment both conditions coincided --
not from the action queue, which always kept both items, only from this compact summary field.
The identical pattern existed a second time: `detect_ppq_findings` unconditionally overwrote
`elements["licensure"]`, which could equally have erased a genuine credential discrepancy (fix
round 2's new check) the moment a PPQ "Yes" answer was also present on the same file. Neither
pattern is exercised by any real case in the three batches (no application currently has two of
these conditions coinciding), so this does not change any batch's sealed output -- found by
re-reading the code with the question "what happens when two of these fire on the same file,"
not from an observed failure.

Fixed with one small helper, `_flag_element`, applied at all four of `process_application`'s
element-overwrite sites (history-discrepancy, credential-discrepancy, eligibility-mismatch,
PPQ-finding): an element is only ever claimed by one of these checks if nothing has already
flagged it (i.e. it's still `resolved` or `outstanding`). Whichever concern is detected first in
the function's fixed code order keeps the slot; every later concern still queues its own action
item regardless, so nothing is ever silently dropped from `action_queue` -- only the previous
unconditional-overwrite behavior on the compact `elements` field is gone. Tests:
`tests/test_engine_orchestration.py` (`test_eligibility_mismatch_does_not_clobber_an_existing_certification_finding`,
`test_ppq_finding_does_not_clobber_an_existing_licensure_discrepancy`), each confirmed failing
against the prior unconditional-overwrite code before the fix.

Separately: intake completeness condition 3 (interview, 02:14 PM) is "a privilege request naming
at least one group from the *current* criteria" -- `missing_intake_items` previously only checked
that a privilege request existed at all, never that it actually cited the current version. Added
`intake.current_criteria_version` to `deliverables/rules.md` (value `LARK-PRIV-2026.1`, sourced to
the interview turn, 05:23 PM, where that document was shared and named) and a check: a privilege
request whose `criteria_version_cited` is populated but names a different version now also counts
as missing condition 3. A blank/absent `criteria_version_cited` is not treated as stale -- same
leniency as this function's other data-derived checks. No real case in any of the three batches
currently cites anything but the current version, so this does not change any batch's sealed
output either. Test: `tests/test_engine_intake.py`
(`test_privilege_request_citing_a_superseded_criteria_version_is_a_missing_item`, plus a guard
test confirming the leniency for blank citations doesn't regress).

Re-ran the full engine across all three batches before and after this round and diffed every
application's `status` and all six `elements` against the currently-sealed snapshots: the only
diffs are the four already-known, already-documented fix-round-1 changes (`APP-2026-022`'s and
`APP-2026-036`'s `education`/`experience`, and their consequent `status` changes) -- nothing new
from this round.

## Fix round 4 -- five more office documents, read for the first time (2026-10-05)

Five more documents named in the interview but never opened (same gap as LARK-ATT-2026.1, caught
later): LARK-AUTH-2026.1 (reserved authority), LARK-PRIV-2026.1 (privilege criteria), LARK-APP-2026.1
(application form), LARK-REF-2026.1 (peer reference form), and the office's export-format note.
All five now on file at `docs/office-documents/`, cited in `deliverables/rules.md`.

1. **Decision admission** (`scripts/engine.py:admit_decision`). `rules.md` previously recorded
   this as an invented "session decision" ("the interview never covered the authority roster") --
   it did (05:19-05:23 PM), the document was simply never opened. Replaced with the real roster:
   three bodies, not two (added Credentials Committee); every decision checked against the named
   individual's role *and* term window, including the Vice-Chair's calendar-year-2026-only
   designation. No real decision fails this check.
2. **Eligibility-question detection** (`scripts/engine.py:detect_eligibility_mismatch`, rewritten).
   Replaced crude keyword-overlap with LARK-PRIV's real 7-rule procedure (board+specialty+training
   match, board-eligible exception scoped to PRIV-FM/IM/HOSP/PED, PRIV-CARD's fellowship+residency
   compound rule, current-experience explicitly excluded). **This one changes real sealed output
   -- 5 applications across the three batches** (independently verified by the project owner,
   including a full trace of `APP-2026-011`/`APP-2026-012`). Found and fixed in the process: the
   prior code flagged a mismatch if *any* requested privilege was unsupported rather than only
   when *none* were (rule 6's actual threshold), and an inclusive-date-range off-by-one in
   training-month arithmetic (`_training_months`).
3. **Certification blank `expiry_date`** -- confirmed already correct (the fix-round-2 code treats
   a blank as "never expires," matching the export note's explicit instruction); locked in with a
   regression test.
4. **WA licensure join key** (`scripts/engine.py:resolve_licensure`). The export note states the
   WA lookup's only reliable join is name+birthyear, not the declared licence number (the WA
   export "carries no practitioner identifier"). The prior number-based join agreed with the
   correct join on all 45 real WA-declared credentials (re-validated after a methodology bug in
   the first validation pass incorrectly applied the WA join to out-of-state credentials too, which
   was caught and corrected before implementing anything). Fixed anyway, since the agreement was
   coincidental, not structural -- a declared number that didn't match the board's own format would
   previously have produced a false "no WA credential" result. Absence is now also reported as
   "confirmed absent," not phrased as unresolved data (export note: "The absence is the answer, not
   a data problem").
5. **Referee working-address wording** (`scripts/engine.py:missing_intake_items`). The prior
   message ("...with a working address each") implied address was being checked; it never was --
   there's no address column anywhere in the export. Reworded, and documented as a third disclosed
   structural-check gap in `rules.md`, matching the existing pattern for the other two.

Re-ran the full engine across all three batches before and after: 14 total status/element diffs,
all traced to item 2 above (`APP-2026-011`, `APP-2026-012`, `APP-2026-022`, `APP-2026-026`,
`APP-2026-032`, plus their consequent `status` changes in later batches) -- independently verified
correct by the project owner. Items 1, 3, 4, 5 are confirmed inert on current sealed output.

## Fix round 5 -- remaining priority-5 items, finished rather than left open (2026-10-05)

The project owner required the three priority-5 items from fix round 4 be fully implemented, not
left as "confirmed inert, documented" findings, plus a check on disposition admission that wasn't
explicitly in round 4's scope.

1. **Disposition admission** (`scripts/engine.py:admit_disposition`, new). LARK-AUTH-2026.1 covers
   the Clinical Director individually (name, role, term) the same way it covers committee/Governing
   Body signatories -- but `apply_dispositions` never checked a disposition's `recorded_by` against
   anything at all, unlike `admit_decision`. Fixed: a disposition recorded by anyone but Dr.
   Marguerite Oyelaran, MD, or dated outside her 2025-07-01 to 2027-06-30 term, is now refused
   (never clears a finding, never discontinues) and raised to the Medical Services Professional. No
   real disposition fails this check.
2. **Gap-explanation matching** (`scripts/engine.py:_gap_is_explained`). Was matching against
   `correspondence.csv`'s office-authored `subject` index via substring containment; LARK-APP-2026.1
   Section F requires matching the applicant's own letter's stated `**Period explained:**` dates
   exactly. Fixed to read the actual letter document. Confirmed against all 4 real gap-explanation
   letters (no behavior change) plus a new synthetic test proving a near-miss period (one day off
   at each end) is correctly rejected, which the old substring check could not distinguish from the
   real thing.
3. **Peer-reference currency** (`scripts/engine.py:resolve_references`). Was measuring staleness
   against the batch's `as_of`; LARK-REF-2026.1 is explicit the reference point is "the date the
   file is presented to the Governing Body." Fixed: `process_application` now computes the latest
   Governing Body `decision_date` on file for the current revision and passes it through as
   `currency_date`, falling back to `as_of` before any such decision exists. No real reference's
   currency verdict changes either way (checked against every admitted Governing Body date).
4. **PPQ declared-vs-verified mismatch** (`scripts/engine.py:detect_ppq_verification_mismatch`,
   new). LARK-APP-2026.1 Section I: a verified "Yes" against a declared "No" gets a specific office
   procedure (confirm in writing or revise) -- distinct from both the plain any-PPQ-answered-Yes
   finding check and the date/issue-date discrepancy checks. Scoped to PPQ-1 only (licence board
   action), the one PPQ with a verifiable cross-reference in this export. **Real case, confirmed
   firing correctly in all three batches**: `APP-2026-015` declared PPQ-1 "No";
   `licence-lookup-wa.csv` shows `actiontaken: "Yes"`; the office's own letter
   (`2026-04-02_confirm-disclosure_APP-2026-015.md`) is this exact procedure already happening by
   hand. Queues an Applicant-owned action item; does not touch element state, since
   `resolve_licensure` already independently surfaces the board action as a `licensure` finding.

Re-ran the full engine across all three batches before and after this round: the only diffs remain
the same 14 already reported and explained in fix round 4 -- none of this round's four fixes
changes any `status` or `elements` value on its own, confirmed both by this diff and by direct
inspection of `APP-2026-015`'s action queue across all three batches (the PPQ mismatch item appears
correctly every time).

**Process note, logged honestly:** test-first-confirm-RED discipline was followed for disposition
admission and the PPQ mismatch check (tests written, confirmed failing against the pre-fix code,
then implemented). It was not followed for gap-matching or reference currency -- the code change
was made first in both cases, with tests added afterward rather than confirmed RED beforehand. Both
fixes were still validated by full-suite passing and the real-data re-validation above, but the
sequencing itself did not meet the standard asked for. The same lapse occurred for several fixes in
round 4 (the WA join key, the fellowship entry-type fix, the referee-address wording).

## Fix round 6 -- a real bug the status/elements-only diff let through (2026-10-05)

Round 5's verification claimed items 1-4 were "inert" based on diffing only `status` and
`elements` against the currently-sealed snapshots. The project owner caught that this check was
too narrow: `action_queue` isn't covered by "status or elements," and the PPQ-1 mismatch check
(round 5, item 4) **does** add a new item to `APP-2026-015` in batches 2 and 3 -- "inert" was
wrong, not just incomplete.

**The real bug**, found by the project owner tracing `APP-2026-015`'s full letter trail (not just
the CSVs): `application-disclosures.csv`'s declared PPQ-1 answer never changes once filed
(office-note-2026-03-16-export-format.md -- a correction arrives as correspondence, not a new
application revision, so the declared field stays frozen at "No" forever). The round-5 check only
ever compared declared-vs-verified, so once it started firing it had no way to ever stop --
including after the Clinical Director's own disposition says she read the applicant's written
confirmation and acted on it
(`office-exports/batch-03/dispositions/2026-05-06_disposition_APP-2026-015.md`: "I have read...
the applicant's written confirmation of 2026-04-20... Present the file to the Executive
Committee"). The action queue would have kept telling the Medical Services Professional to chase
a confirmation the office already has on file.

**Fixed**: `detect_ppq_verification_mismatch` now stops once either human-record signal exists --
any disposition on file for the application (deferring to the Clinical Director's review, the
same "consume the human record once it exists" precedent `apply_dispositions`/`admit_disposition`
already follow), or, short of that, an inbound `confirm-disclosure-reply` letter from the
applicant. Tests written first and confirmed failing against the pre-fix code (3 new tests:
stops-on-disposition, stops-on-reply-letter, still-fires-before-either-signal), then implemented.
Recomputed `APP-2026-015`'s action queue directly across all three batches: fires in batch 1 and
batch 2 (correctly -- neither signal exists yet), stops in batch 3 (correctly -- both exist).

**Re-verification, done properly this time**: diffed the complete recomputed `ApplicationRecord`
(`status`, `elements`, `packet_presentable`, `approval_decision_id`, `activation`,
`monitored_conditions`, `decisions`, and `action_queue` -- every field `to_dict()` produces, not a
hand-picked subset) against the currently-sealed snapshots, for every application, across all
three batches. **33 total line-level diffs**, not the 14 previously reported (status/elements only
undercounts because several applications carry an `action_queue` difference without their compact
`elements`/`status` changing at all -- exactly the class of bug this missed the first time). Traced
every one:

- 2 new, previously-untraced but **correct** consequences of the LARK-PRIV rewrite (round 4, not
  this round), found only because this fuller diff surfaced them: `APP-2026-010` (PRIV-PED,
  board-eligible) correctly shows an unsupported-privilege action item in batch 1 only, because its
  residency verification (`VR-1001`) doesn't land until batch 2 -- the identical
  self-correcting pattern already verified for `APP-2026-011`/`APP-2026-012`, just not
  individually checked for this application before. `APP-2026-027` (PRIV-GS, inactive surgical
  certification) correctly shows the item in batches 1-2 and stops in batch 3, because the
  Clinical Director's disposition ("Offer the applicant the opportunity to amend the privilege
  request") is exactly what happens: revision 2 in batch 3 requests PRIV-FM instead, which the
  applicant's active family medicine certification and verified residency do support.
- The remaining diffs are action-queue-level restatements of status/element changes already
  reported and explained in round 4 (`APP-2026-011`, `APP-2026-012`, `APP-2026-022`, `APP-2026-026`,
  `APP-2026-032`, `APP-2026-036`) -- not new information, just visible in a field the earlier check
  didn't look at.
- `APP-2026-015`'s PPQ-1 item: present in batches 1-2 (pre-fix round, unchanged by round 6's own
  fix -- the item is *supposed* to fire there), gone in batch 3 (round 6's fix, confirmed above).

**Priorities 1-3 from round 5, re-verified the same full-record way, as instructed**: disposition
admission, gap-matching, and peer-reference currency produce **zero** diffs anywhere in the full
`to_dict()` comparison above -- not one `action_queue`, `decisions`, or `monitored_conditions` line
changes because of any of the three. Confirmed inert, this time checking the whole record rather
than the two fields that let the PPQ-1 bug through.

Full test suite: 142 passed.

## Resealing status

As of this entry, **no batch has been resealed** -- `deliverables/snapshots/`,
`deliverables/state/`, and `deliverables/run-log.md` are all still exactly as they were before this
whole redo-audit session, per the project owner's explicit instruction not to reseal until every
fix across all rounds was in. All six fix rounds' tests pass together (142 passed; the three
`test_e2e_batch_0N.py` files are excluded from routine runs during this window because they perform
the actual real run and would otherwise either append spurious "blocked" run-log entries or require
`--force-resupersede` prematurely -- both avoided on purpose). Resealing, with the proper
`--force-resupersede` procedure (new `snapshot_id`s, prior sealed bytes preserved under
`batch-0N.superseded-<timestamp>.json`, `run-log.md` recording which run superseded what and why),
is the next and final step.
