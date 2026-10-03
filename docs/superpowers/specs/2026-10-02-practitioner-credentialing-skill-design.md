# Practitioner credentialing Agent Skill — design

Status: approved by user in chat (2026-10-02). Implementation plan to follow via writing-plans.

## 1. Scope and intent

Build a reusable Agent Skill that runs Larkhollow Community Hospital's initial-appointment
credentialing file from application intake to recorded appointment and active privileges, per
`README.md` and the full assignment doc (Challenge E). The Skill reads one closed export batch
plus the state the previous run left behind, and produces the next state, a sealed snapshot
(`snapshot.schema.json`), and a human action queue. It is run three times, once per supplied
batch, with the third run resuming from the second's output rather than re-reading batch 1.

Five judgments are never computed by the Skill — they only ever become action-queue entries for
a named human owner, consumed only once a corresponding human record (disposition/decision)
exists:
1. Whether a gap explanation is satisfactory.
2. Whether a finding is disqualifying.
3. Whether to discontinue an application on eligibility grounds.
4. Whether to recommend appointment and which privileges.
5. Whether to grant, modify, defer or deny.

## 2. Rule sourcing policy (binding on `deliverables/rules.md`)

Every rule.md entry traces to either:
- A specific interview turn in `interviews/project-e-practitioner-credentialing-20261002-2128.md`
  (quoted or closely paraphrased, with a turn reference), or
- An explicit decision the user (acting as the project owner) made in this build session, recorded
  as such — never attributed to the interview or to a document the interview didn't actually quote.

Rules visible only in office correspondence/letters/dispositions/decisions (not the interview, not
a session decision) are **not** encoded as enforced engine behavior. They are listed in
`rules.md` under "Observed but not encoded" so the gap is visible, and the corresponding element
simply does not get the extra check — it still goes through the ordinary attempt/finding/discovery
machinery, so the worst case is the Skill being a little less strict than the office would be by
hand, never silently wrong in the other direction. Known examples of this (logged there, not
implemented): peer-referee recency ("worked directly within the past two years") and "not employed
by applicant's current practice" from the deferral-chase letter.

One exception, confirmed explicitly by the user as a session decision rather than an interview
rule: a peer-reference reply with `related_or_partner = Yes` is excluded from the count toward the
two required references. This is a direct, mechanical field check (not an inferred threshold) and
is labeled in `rules.md` as a session decision, with the office's own data field as its basis.

Rules confirmed as session decisions (asked and answered 2026-10-02, see chat), each labeled as
such in `rules.md`, never as "from the interview":
1. A resolved `references` element whose reply's `signature_date` is more than 2 years before the
   snapshot's `as_of` reverts to `outstanding` (matches the office's own stated two-year
   presentation/signature window, confirmed by the user).
2. Decision admission: admit a decision record only if (a) its issuing body matches its outcome
   type — Executive Committee of the Medical Staff → `recommended`; Governing Body →
   `approved`/`approved-with-conditions`/`deferred-pending-information`/`denied` — (b) it carries a
   named signatory and role, and (c) it is not a duplicate decision for the same
   application+revision. Anything else is refused, naming the first condition that failed. (This
   exists to catch real cases in the data, e.g. an Executive-Committee-issued `approved` decision,
   which is inadmissible under this check.)
3. Appointment cycle length: 2 years from `effective_date` to `cycle_end`.
4. Eligibility-question auto-detection: if nothing in an applicant's declared/verified training,
   residency, or certification supports a requested privilege's clinical area, the relevant
   element is set to `eligibility-question` and routed to the Clinical Director. The Skill never
   decides the outcome — only flags the mismatch (matches the observed disposition pattern for
   APP-2026-029 / APP-2026-027).
5. Accepted sources: any non-applicant source already named in the office's own data (the
   organization/contact the office actually sent the request to) is treated as accepted. The
   Skill does not attempt to validate against a closed list it was not given.
6. Attempt cadence (up to 3 requests, ≥21 days apart, silence never a pass) applies only to the
   three elements the office actually logs attempts for: experience (`affiliation-and-employment`),
   education (`education-and-training`), and references (`peer-reference`). Licensure is resolved
   purely by whether a current, matching board record exists at `as_of` (no attempt ceiling).
   Certification is resolved once a reply exists in `certification-replies.csv`; absent one it
   stays `outstanding`, re-checked every batch, with no attempt ceiling (the office doesn't log
   attempts for it).

Interview-sourced rules (full list goes in `rules.md` with turn references):
- Intake: 9 completeness conditions (signed/dated application; signed/dated Authorization and
  Release; a privilege request naming ≥1 group from current criteria; a current CV; every PPQ
  answered yes/no with a written explanation behind every "yes"; continuous declared history from
  professional school with explanations for gaps ≥30 days; ≥2 peer referees with a working address
  each; a verification contact on every declared affiliation/employer; every licence/certification
  declared).
- Missing-item letter starts a 30-calendar-day clock from the letter's date; no complete reply by
  the deadline → `ineligible-clock-expired`.
- An unexplained declared-history gap ≥30 days is returned immediately as `returned-incomplete`
  (no clock — it's a direct return, evidenced by the office's own return-incomplete letter, cited
  as a worked example of the stated 30-day-gap completeness condition, not as a new rule).
- Reconciliation: any discrepancy between the application, the CV, and incoming verifications is
  never resolved by picking a value — the applicant must resolve it in writing or amend the
  application; both values stay on file either way. No clock stated for this.
- Six verification elements: licensure, education, experience, time gaps, board certification,
  professional peer references.
- The applicant can never be the source for their own credentials; sources must meet the office's
  accepted-source criteria (closed list not available — see session decision 5 above for how the
  Skill approximates this).
- Up to 3 verification requests per source, ≥21 days apart; a source stays outstanding until a
  reply arrives; silence is never a pass.
- Areas left to a person, not a rule: the five protected judgments listed in §1.
- Export batch boundaries and dates (batch 1: through 2026-03-15, exported 2026-03-16; batch 2:
  2026-03-16–2026-04-19, exported 2026-04-20; batch 3: 2026-04-20–2026-05-17, exported 2026-05-18).

## 3. Repository layout

```
SKILL.md                              # the Agent Skill contract (name/description, inputs,
                                       # invocation, human-authority boundary, outputs,
                                       # failure/re-run behaviour, pointers to code/references)
README.md                             # setup, exact run/resume commands, output semantics,
                                       # verification instructions, handoff notes
deliverables/
  rules.md                            # human-readable + machine-parsed rule register (§2)
  verification.md
  run-log.md
  snapshots/
    batch-01.json
    batch-02.json
    batch-03.json
  state/
    batch-01.state.json               # engine's own continuity ledger — not schema-governed
    batch-02.state.json
    batch-03.state.json
scripts/
  run_batch.py                        # CLI entrypoint
  model.py                            # Application / Element / Decision / etc. dataclasses
  parsers.py                          # CSV + markdown document readers for one batch folder
  rules.py                            # parses deliverables/rules.md's yaml blocks into a dict
  engine.py                           # the state machine (§4)
  snapshot.py                         # builds + validates output against snapshot.schema.json
  action_queue.py                     # action-queue construction helpers
tests/
  ...                                 # unit tests per rule + end-to-end tests per batch
```

`scripts/` uses only the Python standard library plus `jsonschema` (schema validation) and
`pyyaml` (parsing rules.md's fenced yaml blocks); both documented in `README.md` with a
`requirements.txt`.

## 4. Engine — state machine per application

**Intake.** Evaluate the 9 completeness conditions against the latest revision's declared data.
Any missing/unsigned/unexplained item → `intake-incomplete`; the engine queues "send missing-items
letter naming every missing item" for the MSP (it never drafts or sends the letter itself). Once
`correspondence.csv` shows the outbound letter, the clock is tracked from that letter's date. No
complete reply within 30 days → `ineligible-clock-expired`. An unexplained ≥30-day declared-history
gap is returned immediately as `returned-incomplete` (no clock).

**Reconciliation / six elements.** For each of licensure, education, experience, gaps,
certification, references: compute state per the rules in §2/§3, using the structural source
mapping discovered in the data —
- licensure: join `declared-credentials` (credential_class=licence) against
  `licence-lookup-wa.csv` / `licence-lookup-other-states.csv`; current + matching + no unresolved
  board action → `resolved`; board action present → `finding`; no match → `outstanding`.
- education / experience: join `declared-history` entries against `verification-replies.csv`
  (by `entry_id`) and track attempts via `verification-attempts.csv`.
- certification: join `declared-credentials` (credential_class=certification) against
  `certification-replies.csv`.
- references: join `peer-referees.csv` against `peer-reference-replies.csv`; exclude
  `related_or_partner = Yes` replies from the required count of 2 (session decision); apply the
  2-year signature staleness reversion (session decision).
- gaps: evaluated at intake (≥30-day unexplained gap) and, once an explanation is received, held
  as a `finding` pending the Clinical Director's satisfactory/not determination (never
  auto-resolved).
- Any PPQ answered "Yes", or a board disciplinary/monitoring action, or a privilege request with no
  supporting declared/verified training-or-certification (session decision 4) → `finding` /
  `eligibility-question` on the relevant element, routed to the Clinical Director; the engine
  queues the review and only resolves the element once a disposition document exists and is
  parsed (see below).

**Discrepancy.** Any mismatch between application/CV/verification values on the same fact →
`discrepancy`; cleared only by a written explanation or an amended revision touching that fact.

**Disposition parsing.** Clinical Director disposition documents are matched against a small set
of known literal phrasings (e.g. "Discontinue the application" / "Do not discontinue" / "present
the file to the Executive Committee ... and the Governing Body" / "I record no bar to appointment
and no condition"). A disposition whose text doesn't match a known pattern produces an
action-queue item asking a human to interpret it manually — it is never guessed.

**Revisions.** A new revision carries forward every element's prior state except elements whose
underlying declared rows (credentials / history / disclosures / privilege-requests relevant to that
element) actually changed between the prior and current revision — those reset to `outstanding`
and re-verify. This is a mechanical diff against the state ledger, not a business threshold.

**Packet / decision / activation.** `packet_presentable = true` once all six elements are
`resolved`, bound to the current revision, and no admitted outcome governs it yet →
`status = packet-presentable`. Decision records are admitted/refused per session decision 2.
`approval_decision_id` only ever names an admitted Governing Body `approved` /
`approved-with-conditions` decision. On admission, `activation` is computed with `cycle_end`
= `effective_date` + 2 years (session decision 3). `denied` / `deferred-pending-information`
admitted decisions drive `status = denied` / `deferred` respectively. A decision record that the
admission check refuses (body/outcome mismatch, missing signatory, or duplicate) drives
`status = decision-inadmissible` for that revision — provided no other admitted Governing Body
outcome already governs it — with the refusal reason recorded in that decision's `reason`.

**Terminal statuses.** `withdrawn` on an applicant withdrawal letter; `discontinued` on a Clinical
Director disposition that says so — both override everything else for that file from that point
on.

## 5. Run semantics, failure classification, resume

`scripts/run_batch.py --batch N [--state deliverables/state/batch-0{N-1}.state.json]`:
1. Loads the prior state ledger (absent only for batch 1).
2. Reads `office-exports/batch-0N/` per its README.
3. Runs the engine over every application touched by this batch's rows plus every application
   still open from the ledger.
4. Writes `deliverables/state/batch-0N.state.json` (the next ledger) and
   `deliverables/snapshots/batch-0N.json` (validated against `snapshot.schema.json` before being
   written).
5. Classifies the run as `supported` / `partial` / `blocked` per the assignment's definitions and
   appends one entry to `deliverables/run-log.md` (command, batch, timestamp, files consumed,
   files produced/refreshed, every failure with its affected scope). `deferred` files are a
   correct result, called out in the log, not a run-outcome category.
6. On `blocked`, no snapshot is written/overwritten; the previously sealed snapshot stands, and the
   run log records the attempt, the error, and the affected scope.
7. Re-running a batch that changes nothing leaves the already-sealed snapshot's bytes untouched. A
   real fix regenerates that snapshot and every later one under new `snapshot_id`s, preserves each
   superseded occurrence under a distinct name with unchanged bytes, and the run log records which
   run superseded which file and why.

## 6. Verification approach (`deliverables/verification.md`)

For each batch: re-derive at least one quantity by a method other than the Skill's own code (e.g.
hand/spreadsheet-recount of how many applications are `active` vs `in-verification` at that
`as_of`, or a recount of attempt counts for one source from the raw CSV), compare against the
snapshot, and record what was checked, how, what was found, and what changed as a result. Also
spot-check: every `decisions[].decision_id` traces to the office's own record; every
`approval_decision_id` names an admitted approval; every sealed snapshot validates against
`snapshot.schema.json`.

## 7. Known limitations (to be stated plainly in `rules.md` / `README.md`)

- Peer-referee recency ("worked directly within the past two years") and the "not employed by the
  applicant's current practice" condition seen in one deferral-chase letter are not enforced —
  observed only in correspondence, not the interview or a session decision.
- The accepted-source closed list (LARK-ATT-2026.1) was not read into the interview; the Skill
  approximates "accepted" as "non-applicant source already in the office's data," per session
  decision 5.
- Privilege criteria specifics (LARK-PRIV-2026.1) were not read into the interview; eligibility
  mismatch detection (session decision 4) is a coarse "nothing supports this privilege area" check,
  not a citation-level criteria match.
