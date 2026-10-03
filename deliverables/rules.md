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

## Session decisions (made by the project owner in this build session, 2026-10-02 — NOT from the
interview; recorded here so the provenance is honest)

### Peer-reference staleness window

```yaml
id: references.staleness_years
value: 2
source: >
  Session decision, 2026-10-02: a resolved references element whose reply's signature_date is
  more than this many years before the snapshot's as_of reverts to outstanding. Confirmed by the
  project owner after the Skill-builder found the "two-year signature date" mentioned in the
  interview's opening remarks lacked a stated consequence there.
```

### Appointment cycle length

```yaml
id: appointment.cycle_years
value: 2
source: >
  Session decision, 2026-10-02: activation.cycle_end = effective_date + this many years. Not
  stated in the interview; the project owner supplied this value directly when asked.
```

## Other session decisions (not numeric — no yaml block, but binding on scripts/engine.py)

- **Decision admission.** Admit a decision record only if: its issuing body matches its outcome
  type (Executive Committee of the Medical Staff -> `recommended`; Governing Body ->
  `approved` / `approved-with-conditions` / `deferred-pending-information` / `denied`), it carries
  a named signatory and role, and it is not a duplicate decision for the same application and
  revision. Refuse anything else, naming the first condition that failed. Session decision,
  2026-10-02 — the interview never covered the authority roster or decision-admission criteria.
- **Eligibility-question auto-detection.** If nothing in an applicant's declared or verified
  training, residency, or certification supports a requested privilege's clinical area, set that
  element to `eligibility-question` and route it to the Clinical Director; the Skill never decides
  the outcome. Session decision, 2026-10-02.
- **Accepted sources.** Any non-applicant source already present in the office's own data (the
  organization/contact the office actually sent the request to) is treated as an accepted source.
  The Skill does not validate against the closed list named in the interview (LARK-ATT-2026.1)
  because that document was not read into the interview. Session decision, 2026-10-02.
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
- Reconciliation discrepancy handling (interview, Renata Kowalczyk, 2026-10-02 02:23 PM): "Where
  any discrepancy arises among these sources, I never pick a value or assume one is correct...
  Both the declared date and the verified date stay in your file either way." No clock is stated
  for discrepancy resolution, and none is implemented.

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
