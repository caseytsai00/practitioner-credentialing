# Credentialing rules register

Every numeric or temporal threshold the Skill applies is defined below as a fenced `yaml` block
with an `id` the code reads by name (`scripts/rules.py:load_rules`) and a `source` line saying
exactly where it came from. Structural checks that aren't a number to tune (e.g. "is there a
privilege request row at all") are implemented directly in code, are not listed as yaml blocks
here, and are documented in the "Structural checks" section below with the interview statement
that backs each.

No case-specific threshold is hardcoded in `scripts/engine.py`; every value engine.py reads about
timing, counts, or windows comes from this file via `scripts/rules.py:load_rules`.

## Rules sourced from the interview

### Missing-items letter clock

```yaml
id: intake.missing_items_clock_days
value: 30
source: >
  Interview, Renata Kowalczyk, 2026-10-02 02:17-02:20 PM: "I send a written request to the
  applicant explicitly naming every missing item or clarification needed, and I start a
  thirty-day clock on the date of that letter... If 30 calendar days pass from the date on my
  written request without a complete reply, the application is considered incomplete and
  ineligible for processing and is returned."
```

### Unexplained declared-history gap

```yaml
id: intake.unexplained_gap_days
value: 30
source: >
  Interview, Renata Kowalczyk, 2026-10-02 02:14 PM, completeness condition 6: "a declared
  history running continuously from professional school with explanations for gaps of thirty
  days or more."
```

### Verification attempt ceiling and spacing

```yaml
id: verification.attempt_max_count
value: 3
source: >
  Interview, Renata Kowalczyk, 2026-10-02 05:20 PM: "I log up to three requests at least
  twenty-one days apart, and the source remains outstanding until a reply arrives, as silence is
  never a pass."
```

```yaml
id: verification.attempt_min_spacing_days
value: 21
source: >
  Interview, Renata Kowalczyk, 2026-10-02 05:20 PM (same turn as above).
```

Applies only to the three elements the office logs attempts for: experience
(`affiliation-and-employment`), education (`education-and-training`), and references
(`peer-reference`) — see session decision 6 below for why licensure and certification are
excluded.

### Minimum peer referees

```yaml
id: references.required_count
value: 2
source: >
  Interview, Renata Kowalczyk, 2026-10-02 02:14 PM, completeness condition 8: "at least two peer
  referees with a working address each."
```

### Current privilege-criteria version

```yaml
id: intake.current_criteria_version
value: LARK-PRIV-2026.1
source: >
  Interview, Renata Kowalczyk, 2026-10-02 05:23 PM: shared "Privilege criteria — initial
  appointment (LARK-PRIV-2026.1)" as the office's privilege criteria document. Every
  privilege-requests.csv row's criteria_version_cited across all three real batches cites exactly
  this version. Intake completeness condition 3 (02:14 PM) is "a privilege request naming at least
  one group from the current criteria" — the "current" qualifier was previously unchecked (see
  fix note below).
```

Fixed 2026-10-04: `missing_intake_items` only ever checked that a privilege request existed at
all, never that it actually cited this version. A privilege request whose `criteria_version_cited`
names an older version now also counts as missing condition 3. A **blank or absent**
`criteria_version_cited` is not treated as stale — only an explicit, populated, non-matching
citation is — consistent with every other completeness check's treatment of data the office's
export simply doesn't carry (see "Structural checks" below). No real case in any of the three
batches currently cites anything but the current version, so this does not change any batch's
sealed output.

## Session decisions (made by the project owner in this build session, 2026-10-02 — NOT from the
interview; recorded here so the provenance is honest)

### Peer-reference staleness window

```yaml
id: references.staleness_years
value: 2
source: >
  Session decision, 2026-10-02: a resolved references element whose reply's signature_date is
  more than this many years before the reference's currency date reverts to outstanding.
  Confirmed by the project owner after the Skill-builder found the "two-year signature date"
  mentioned in the interview's opening remarks lacked a stated consequence there.
```

**Correction, 2026-10-05.** The two-year window itself was already right, but what it's measured
*against* was wrong: `docs/office-documents/LARK-REF-2026.1-peer-reference-form.md`, "Currency":
"A reference is current if the signature date is within two years of the date the file is
presented to the Governing Body... not the date we receive the form." `resolve_references`
measured against the batch's `as_of` instead — `scripts/engine.py:resolve_references` now accepts
a `currency_date`, computed by `process_application` as the latest Governing Body `decision_date`
on file for the application's current revision (regardless of whether that decision is ultimately
admitted — the roster check governs whether the *decision* counts, not whether the GB actually
sat and looked at the file that day); before any Governing Body decision exists for this revision,
there is no presentation date yet, so `as_of` remains the fallback. No real application in any of
the three batches has a reference whose currency verdict flips between the two reference points
(checked across every signed reply against every admitted Governing Body decision date), so this
does not change any batch's sealed output.

### Appointment cycle length

```yaml
id: appointment.cycle_years
value: 2
source: >
  Session decision, 2026-10-02: activation.cycle_end = effective_date + this many years. Not
  stated in the interview; the project owner supplied this value directly when asked.
```

## Other session decisions (not numeric — no yaml block, but binding on scripts/engine.py)

- **Decision admission.** The office's own authority roster, "Reserved authority — who holds what
  (LARK-AUTH-2026.1)", effective 2026-01-01, is now on file at
  `docs/office-documents/LARK-AUTH-2026.1-reserved-authority.md`. **Correction, 2026-10-05**: this
  entry previously said "the interview never covered the authority roster or decision-admission
  criteria" and recorded this as an invented session decision — it did cover it (05:19-05:23 PM,
  the document links shared there), the document was simply never opened until now. The rule below
  is the real one, not an approximation:
  - Three bodies, not two: **Credentials Committee** and **Executive Committee of the Medical
    Staff** may each record `recommended`, `not-recommended` or `deferred-pending-information` —
    never an approval. **Governing Body** alone may record `approved`, `approved-with-conditions`,
    `deferred-pending-information` or `denied`. (The manual, Section 12: "All signatories should
    utilize a 'recommend' selection, with only the Chair of the GB or their designee using the
    'approval' selection.")
  - A decision names the application's current revision (one naming a since-superseded revision is
    refused with that reason, never silently dropped).
  - A decision's `(signatory, role)` must match an entry on the roster **for that body**, and the
    decision's own `decision_date` must fall within that entry's term — the roster's own opening
    line: "A record's own claim of authority is not evidence of it." The Vice-Chair, Governing
    Body's authority is a one-year designation ("for the calendar year 2026"), distinct from — and
    narrower than — their seat's own term; a decision they sign outside 2026 is refused even though
    they still hold the Vice-Chair role.
  - Among decisions that pass every check above, only the chronologically latest one from its body
    for this application and revision is admitted (an earlier one from the same body is refused as
    superseded by the later one, not as an inadmissible "duplicate", so a real follow-up decision
    after a deferral is never wrongly blocked).
  - Refuse anything else, naming the first condition that failed.
  Current roster (effective 2026-01-01; a future roster version would need its own entry here):
  Credentials Committee — Dr. Anneke Thorvald, MD, Chair, 2025-07-01 to 2027-06-30. Executive
  Committee of the Medical Staff — Dr. Peter Vandermolen, MD, Chair, 2026-01-01 to 2027-12-31.
  Governing Body — Ms. Corinne Batiste, Chair, 2025-01-01 to 2027-12-31; Mr. Desmond Ihejirika,
  Vice-Chair, designated approver 2026-01-01 to 2026-12-31 only.
  **Disposition admission, added 2026-10-05**: the same roster covers the Clinical Director
  individually — "Dr. Marguerite Oyelaran, MD, 2025-07-01 to 2027-06-30: record a disposition on
  a gap explanation, on a high-risk or licensure finding, and on a threshold eligibility
  question; decide whether an application is discontinued" — and `apply_dispositions` previously
  never checked a disposition's `recorded_by` against it at all, unlike `admit_decision`.
  `scripts/engine.py:admit_disposition` now checks `recorded_by` (the office's combined
  "`<signatory>, <role>`" field for dispositions, confirmed against all 5 real disposition
  documents: `"Dr. Marguerite Oyelaran, MD, Clinical Director"`) and the disposition's own date
  against her term the same way decisions are checked; a disposition that fails either check is
  never applied (no finding cleared, no discontinuation), and is raised to the Medical Services
  Professional instead. No real disposition in the three batches is recorded by anyone else or
  dated outside her term, so this does not change any batch's sealed output.
- **Eligibility-question auto-detection.** The office's own privilege criteria, "Privilege
  criteria — initial appointment (LARK-PRIV-2026.1)", in force from 2026-01-01, is now on file at
  `docs/office-documents/LARK-PRIV-2026.1-privilege-criteria.md`. **Correction, 2026-10-05**: this
  entry previously approximated "nothing in declared/verified training or certification supports
  the privilege's clinical area" via crude keyword-token overlap against organization/issuer
  names — the document gives the real, seven-rule procedure, and the token-overlap approximation
  is now replaced with it:
  1. A requested group is supported when the applicant holds a verified certification from one of
     the group's named boards, in the specialty named, `certification_status` Active, **and**
     verified training meets the group's minimum training duration.
  2. Unsupported when neither holds (the office's own finding names the specific group; other
     requested groups are unaffected).
  3. An inactive or expired certification supports nothing, even though it is still verified and
     recorded.
  4. **Board eligible** is accepted in place of an active certification for PRIV-FM, PRIV-IM,
     PRIV-HOSP and PRIV-PED only — and only when the board's reply states in writing that the
     applicant is a candidate in good standing with an eligibility end date, and that date is
     still in the future as of the date checked. Not accepted for any other group.
  5. PRIV-CARD requires **both** a verified cardiovascular disease fellowship and the antecedent
     internal medicine residency; either alone does not support it.
  6. **This is the only rule the Skill itself applies.** When nothing the applicant holds supports
     *any* requested group, this is a threshold eligibility question, raised to the Clinical
     Director; the Skill never discontinues the application itself. Evaluated against what is
     verified at the batch's `as_of` (the document's own words: "on what has been verified at the
     export date"), since the Skill runs before any decision exists and has no decision date to
     check rule 1 against yet.
  7. **Current experience is explicitly excluded from this determination** — "Current competency
     is determined by clinical leadership, not the office," per the manual (Section 6, Subsection
     4, element 8). `scripts/engine.py` never reads a privilege group's "current experience"
     column for any purpose.
  `scripts/engine.py:_verified_training_months` also fixed a real bug surfaced while implementing
  rule 1: a residency `from_date`/`to_date` pair is inclusive at both ends (office note), so
  2010-07-01 to 2013-06-30 is 36 months, not 35 — the prior month-arithmetic undercounted every
  inclusive range by one month.
  `scripts/engine.py:resolve_elements` also now recognizes `entry_type: fellowship` (LARK-APP-2026.1,
  Section D, names it as a valid declared-history entry type) as an education entry — it was
  previously excluded from verification entirely. No real application in any of the three batches
  currently declares a fellowship, so this does not change any batch's sealed output on its own.
- **Accepted sources.** The office's closed source list, "Accepted sources by element — who may
  attest (LARK-ATT-2026.1)", in force from 2026-01-01, is now on file at
  `docs/office-documents/LARK-ATT-2026.1-accepted-sources.md` and is what `scripts/engine.py`
  checks a reply's `attester_organization` against, per element:
  - **Education and training, Board certification:** admissible if the attester is the
    degree-granting/certifying body itself (the entry's own declared organization/issuer), *or* one
    of the table's named designated-equivalent sources (education: ECFMG, FCVS, AMA Physician
    Profile, AOA Physician Profile, National Student Clearinghouse; certification: ABMS, CertiFACTS,
    AMA Physician Profile, AOA Physician Profile, ABPS, ANCC, NCCPA) — checked by name, never by
    whether it happens to match the declared school/board's own name, since none of these will.
  - **Education** additionally admits a **secondary source only on impossibility**: the applicant's
    most recent affiliation (by declared history), where the reply itself states the reason and the
    file already carries evidence the primary/designated-equivalent route is actually impossible (a
    `no-record` reply or an `undeliverable` attempt for that same entry) — not merely unanswered.
    Non-response is never impossibility (table's own words); a source that exists and just hasn't
    replied stays outstanding under the ordinary attempt cadence, full stop.
  - **Licensure:** the office's own `licence-lookup-wa.csv`/`licence-lookup-other-states.csv` are
    themselves primary-source board data (direct board lookups, or — for `licence-lookup-other-states.csv`'s
    `verified_by` field — the issuing board's own verification service in every row observed in all
    three batches); the table lists one designated equivalent (Federation of State Medical Boards
    Physician Data Center) and no secondary source at all ("a state licensing board does not
    close"). No batch's data contains a row that isn't already primary-source, so no additional
    admissibility code was added here — there is nothing in the data's shape to validate a check
    against yet. Flag for a future batch: if a non-board `verified_by` value ever appears, this gap
    needs closing then.
  - **Affiliations and employment:** admissible only if the attester matches the *currently*
    declared employer/affiliation (the table's primary-source row: that employer's own medical
    staff office or HR department) — checked by name-matching, which **is** correct for this
    element specifically, because the entity being verified for an employment entry is the employer
    itself. A reply naming a different organization doesn't fail as "off the table" (an employer's
    HR office is always a legitimate primary-source *type*); it simply doesn't speak to the current
    declared record (e.g. after a revision renames the employer) and the entry stays outstanding
    pending a reply that does. The table's secondary-source row (employer dissolved, no successor)
    and designated-equivalent row (a retained CVO) are documented but not coded against, since no
    batch contains an instance of either to validate a check against.
  - **Every element:** the applicant is never an accepted source (manual Section 6, Subsection 1,
    both rules) — confirmed true throughout `scripts/engine.py` independent of this table: every
    `resolve_*` function requires a row in an independent reply/lookup file before an element can
    resolve; none ever resolves purely from applicant-declared data.
  - A reply from a source that is on neither the primary, designated-equivalent, nor (where it
    exists) secondary-with-impossibility-evidence list is **inadmissible**: recorded as received,
    the entry stays `outstanding`, further requests continue going to an accepted source, and it is
    raised to the Medical Services Professional to decide whether an impossibility route applies —
    per the table's own "What to do with a reply that is not on this table" section. This replaces
    the prior, interview-only approximation ("any non-applicant source already in the office's data
    is accepted"), which the office's real document shows was both too permissive (an inadmissible
    reply like a state medical society's membership file was never flagged) and, in one case, too
    strict (an org-name-match-only check wrongly rejected a textbook-valid secondary source). Both
    corrected 2026-10-04; see `deliverables/verification.md`.
- **Attempt cadence scope.** The 3-attempts/21-days rule above applies only to the three elements
  the office's own `verification-attempts.csv` actually tracks attempts for (experience,
  education, references). Licensure is resolved purely by whether a current, matching board
  record exists at `as_of` (`licence-lookup-wa.csv` / `licence-lookup-other-states.csv`); no
  attempt ceiling applies because there is no live "chasing" of the state board. Certification is
  resolved once a matching row exists in `certification-replies.csv`; absent one it stays
  `outstanding`, re-checked every batch, with no attempt ceiling because the office does not log
  attempts for it. Session decision, 2026-10-02.
- **Related/partner peer references.** A peer-reference reply with `related_or_partner = Yes` is
  excluded from the count toward `references.required_count` above. This is a direct field check
  against the office's own data, not an inferred threshold. Session decision, 2026-10-02.

## Areas the office leaves to a person, never to this Skill

Interview, Renata Kowalczyk, 2026-10-02 05:21 PM: "The areas left to human judgment include
determining if a gap explanation is satisfactory, whether a finding is disqualifying, whether to
discontinue an application on eligibility grounds, and the final decisions made by the Clinical
Director and committees on appointments and privileges." Per the full assignment doc, the fifth
protected judgment is whether to grant, modify, defer or deny. `scripts/engine.py` never computes
any of these five; it only ever emits an action-queue entry naming the owner, and consumes the
resulting human record (disposition or decision) once one exists.

## Structural checks (not thresholds — implemented directly in code, not read from this file)

- Nine intake completeness conditions (interview, Renata Kowalczyk, 2026-10-02 02:14 PM): each is
  a presence/signature check against a specific declared field, implemented in
  `scripts/engine.py:missing_intake_items`. Two conditions cannot be verified from data alone and
  are treated as satisfied whenever at least one supporting row exists — a disclosed
  simplification, not a silent assumption: "every professional practice question answered yes or
  no" (the office's disclosure export only carries questions it asked; we cannot detect a
  question the applicant was never asked) and "every licence and certification the applicant
  holds declared" (we cannot detect a credential the applicant did not declare).
  A third is now equally disclosed, confirmed by `office-note-2026-03-16-export-format.md`:
  "at least two peer referees with a working address each" has **no address data anywhere in
  the export at all** ("The export carries no address column for peer referees"). The office's
  own note states the right framing directly: "a run assesses condition 7 on the named referees
  alone and records the address check as not assessable from the export — neither met nor
  failed." `missing_intake_items` only ever checked the referee *count* — never address, despite
  message wording that implied otherwise until corrected 2026-10-05 ("...with a working address
  each" → "...named"). The address half is genuinely not assessable here; it is the Medical
  Services Professional's own check, done outside this export.
- **Gap-explanation matching, corrected 2026-10-05.**
  `docs/office-documents/LARK-APP-2026.1-application-form.md`, Section F: "Begin the explanation
  with the line Period explained: <from date> to <to date>... the office matches your explanation
  to the period by those two dates and by nothing else." `scripts/engine.py:_gap_is_explained`
  previously matched against `correspondence.csv`'s own `subject` column — an office-authored
  index, not the applicant's letter (the office's own export note warns "It does not tell you
  what they say — you have to open them") — via loose substring containment rather than the
  letter's own stated dates exactly. Now reads the actual letter document (`letters/`,
  `letter_type: gap-explanation`) and requires its own `**Period explained:** <from> to <to>` line
  to match the computed gap's dates exactly. Confirmed against all 4 real gap-explanation letters:
  every one already carries this exact field, and this does not change any batch's sealed output.
- **PPQ declared-vs-verified mismatch, added 2026-10-05.**
  `docs/office-documents/LARK-APP-2026.1-application-form.md`, Section I: "If a verification the
  office receives shows that a Yes was owed and a No was given, the office will contact you to
  confirm the answer before the file goes any further." This is distinct from both the
  date/issue-date discrepancy checks above and from the plain "any PPQ answered Yes" finding
  check (`detect_ppq_findings`) — it compares a declared **No** against independent verified
  evidence. Real case: `APP-2026-015` declared PPQ-1 "No"; the WA board's own lookup shows
  `actiontaken: "Yes"` (a stipulated agreement, `office-exports/batch-01/letters/2026-03-04_board-action_APP-2026-015.md`).
  The office's own letter, `2026-04-02_confirm-disclosure_APP-2026-015.md`, is this exact
  procedure. `scripts/engine.py:detect_ppq_verification_mismatch` is scoped to PPQ-1 only — the
  one of the eight professional practice questions with a verification source directly checkable
  from this export (a licence's board action); none of the other seven have a comparably
  verifiable cross-reference in the data. Queues an Applicant-owned action item (matching the
  existing discrepancy convention) rather than touching element state, since the underlying board
  action is already independently surfaced as a `licensure` finding by `resolve_licensure`.
- Reconciliation discrepancy handling (interview, Renata Kowalczyk, 2026-10-02 02:23 PM): "Where
  any discrepancy arises among these sources, I never pick a value or assume one is correct...
  Both the declared date and the verified date stay in your file either way." No clock is stated
  for discrepancy resolution, and none is implemented.
  - **Scope, as actually implemented** (`scripts/engine.py:detect_discrepancies`,
    `detect_credential_discrepancies`): `from_date`/`to_date` on each declared-history entry
    against `verification_replies`; `declared_issue_date` on each declared credential (licence or
    certification) against the matching `licence-lookup-*.csv` row or `certification-replies.csv`
    reply. A hit sets the relevant element (`education`/`experience`/`licensure`/`certification`)
    to `discrepancy` and queues an Applicant action item naming both values, exactly as the
    interview describes.
  - **Comparing against the curriculum vitae is not implemented** — the office's export carries
    only a CV-received-date flag (`applications.csv:cv_received_date`), never the CV's content
    (confirmed, interview 02:32-02:33 PM: "I cannot share a specific applicant's curriculum vitae
    because it contains private personal data"), so there is nothing to compare it against. This
    narrows "application... CV... and incoming verifications" to "application... and incoming
    verifications" in practice — a necessary simplification given the data available, now stated
    here rather than left implicit.
  - **`declared_expiry_date` is deliberately excluded**, licence and certification alike. Real
    case: `APP-2026-040`'s WA licence (`MD60096330`) renewed between batch 2 and batch 3 —
    `licence-lookup-wa.csv`'s `expirationdate` moved from `2026-04-10` to `2028-04-30`, while
    `firstissuedate` stayed fixed at `2011-06-27` throughout. An expiry date is a live,
    forward-moving fact the issuing board keeps current; the application's declared value is a
    frozen intake-time snapshot. Comparing them would flag every routine renewal after the
    original application as a false discrepancy demanding the applicant's written explanation,
    when nothing was ever misdeclared. (Evidence genuinely *aging* while a file waits — the
    distinct concern this could be mistaken for — is handled separately: see
    `certification.expiry_check` below and `resolve_licensure`'s existing expiry check, both of
    which compare the verified expiry against `as_of` directly and revert to `outstanding`, not a
    discrepancy.) Confirmed by re-running all three batches before and after narrowing this scope:
    zero `licensure`/`certification` element values changed either way except this one false
    positive, which disappeared.
  - **`declared_status` is deliberately excluded.** The application form and the issuing board use
    different vocabularies for the same fact — the application declares "Board certified", the
    board replies "Active" — true of 38 of the 40 real `certification-replies.csv` rows across all
    three batches. Comparing the text directly would flag nearly the entire caseload as false
    discrepancies. The one genuine status disagreement in the data, `APP-2026-027`'s American
    Board of Surgery certification (declared "Board certified", reported "Inactive"), is already
    correctly handled as a `finding` routed to the Clinical Director by `resolve_certification`'s
    own status check — matching the office's own letter, which frames it as a threshold
    eligibility question for the Clinical Director, not something the applicant resolves in
    writing.
  - No real case in any of the three batches currently has a `declared_issue_date` mismatch
    (checked across all 87 declared-credentials rows with a matching lookup/reply row) — this part
    of the check is implemented from the interview's stated rule directly, not from an observed
    failure, and does not change any batch's sealed output.
- **Certification expiry aging** (`certification.expiry_check`, structural — not a tunable
  threshold, so no yaml block): interview, opening remarks, 07:13 PM: "a file sits ready for the
  committee for weeks while a licence expires underneath it or a peer reference passes its
  two-year signature date, and I only notice when I happen to look." `resolve_licensure` already
  re-checked a licence's expiry against `as_of` on every run; `resolve_certification` never did —
  a `certification_status` of `"Active"` only reflected what the board said when it replied, and
  could silently outlive its own `expiry_date`. Fixed 2026-10-04: `resolve_certification` now
  compares `expiry_date` against `as_of` the same way `resolve_licensure` already compared its own
  expiry; an expired certification reverts to `outstanding` (not `finding` — this is stale
  evidence needing a fresh reply, not a disqualifying determination for the Clinical Director to
  judge, the same category a lapsed licence is already in). No real case in the office's three
  batches has an `expiry_date` before any batch's `as_of` (checked across every
  `certification-replies.csv` row) — implemented from the interview's own stated scenario
  directly, and does not change any batch's sealed output.

## Known limitations (observed only in office correspondence, not the interview or a session
decision — deliberately not enforced; see design spec section 7)

- Peer-referee recency ("worked directly with you within the past two years") — seen in
  `office-exports/batch-02/letters/2026-04-16_deferral-chase_APP-2026-034.md` — not enforced.
- "Not employed by [the applicant's] current practice" for a substitute referee — same letter —
  not enforced.
- A trailing gap between the last declared-history entry's `to_date` and the present is not
  checked — only a gap strictly between two consecutive declared entries. The interview's
  completeness condition describes "a declared history running continuously from professional
  school," which a still-open current position already satisfies (no `to_date` to compare), so
  this is a narrow gap in the check rather than a disclosed office rule.
- The Clinical Director action item queued when a professional-practice-question "Yes" answer
  forces a `finding` (see `process_application` in `scripts/engine.py`) is appended
  unconditionally before dispositions are applied, so it can linger in `action_queue` after a
  later disposition resolves the element it concerns — a stale, redundant informational entry,
  not a wrong element state or status. Found and documented during the independent recompute in
  `deliverables/verification.md`; deliberately left as a known limitation rather than a fourth
  fix-and-resupersede cycle.
