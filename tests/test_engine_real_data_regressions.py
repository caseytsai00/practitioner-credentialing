from __future__ import annotations

import os

from scripts.engine import process_batch
from scripts.parsers import BatchData
from scripts.rules import load_rules
from scripts.state import new_ledger

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
AS_OF_BY_BATCH = {1: "2026-03-16", 2: "2026-04-20", 3: "2026-05-18"}

# This module drives scripts.engine.process_batch directly against the real office-exports/
# data, chaining the in-memory ledger across batches exactly as scripts/run_batch.py does --
# but it never writes to deliverables/, so it can be re-run freely to confirm a code fix
# without resealing anything. The real sealed snapshots are only regenerated once, deliberately,
# after every fix in this round is in (see run-log.md / verification.md for that step).


def _run_through(batch_number):
    rules = load_rules(os.path.join(REPO_ROOT, "deliverables", "rules.md"))
    ledger = new_ledger()
    records_by_id = {}
    for n in range(1, batch_number + 1):
        batch = BatchData(os.path.join(REPO_ROOT, "office-exports", "batch-{:02d}".format(n)))
        records, ledger, _warnings = process_batch(batch, ledger, rules, AS_OF_BY_BATCH[n])
        records_by_id = {r.application_id: r for r in records}
    return records_by_id


def test_app_2026_021_education_resolves_via_valid_secondary_source():
    # Real case: ENT-2100/APP-2026-021 (declared-history.csv: medical school, "Cascade Valley
    # College of Medicine"). The college closed 2019-06-30 (verification-attempts.csv ATT-2104:
    # "undeliverable... The institution closed"); FCVS, the designated-equivalent source, replied
    # "no-record" (VR-2104). Per docs/office-documents/LARK-ATT-2026.1-accepted-sources.md's
    # education table, this is exactly when the secondary-source route opens: a reply from the
    # applicant's most recent affiliation (Greyfen Regional Hospital, ENT-2103, the applicant's
    # only open-ended/current employment) stating how it obtained its own verification, with the
    # reason written into the file (VR-2100's notes). This must resolve -- not stay outstanding
    # pending human review -- because the table makes this specific, evidenced case admissible on
    # its own terms. Independent confirmation this is the right call: by batch 3 this application
    # reaches an admitted Governing Body approval (GBD-2026-028) and `active` status with no
    # discrepancy or inadmissible-reply letter ever issued for it -- the office's own downstream
    # process treated this exactly as resolved.
    for batch_number in (1, 2, 3):
        records = _run_through(batch_number)
        if batch_number == 1:
            # The secondary reply (VR-2100) and the FCVS no-record reply (VR-2104) both land in
            # batch 2's verification-replies.csv, not batch 1's -- batch 1 correctly has nothing
            # confirming this entry yet.
            assert records["APP-2026-021"].elements["education"] == "outstanding"
        else:
            assert records["APP-2026-021"].elements["education"] == "resolved", "batch {}".format(batch_number)


def test_app_2026_022_education_stays_outstanding_across_all_batches():
    # Real case: ENT-2201/APP-2026-022 (office-exports declared-history.csv), a residency
    # declared at Westmarch University Medical Center. Its only reply, VR-2201
    # (verification-replies.csv), comes from "Cascade Valley Physicians Society" -- a state
    # medical society confirming "from its own membership file" -- not from Westmarch's own
    # Graduate Medical Education office, which never replied across 3 logged attempts
    # (verification-attempts.csv: ATT-2203, ATT-2204, ATT-2205, all "no response"). Per
    # docs/office-documents/LARK-ATT-2026.1-accepted-sources.md, a state medical society is on
    # neither the primary, designated-equivalent, nor secondary-source list for education (and it
    # is not even the applicant's most recent affiliation, so the secondary-source test doesn't
    # apply regardless); this is a genuinely inadmissible reply, not a stale-but-legitimate one.
    # "Non-response is not impossibility" rules out treating Westmarch's silence as an opening for
    # a secondary route either. This must stay outstanding in all three batches (no later batch
    # ever supplies a reply from Westmarch itself), and the action queue must carry the table's
    # own four-step procedure, not a generic message.
    for batch_number in (1, 2, 3):
        records = _run_through(batch_number)
        record = records["APP-2026-022"]
        assert record.elements["education"] == "outstanding", "batch {}".format(batch_number)
        assert any(
            "not on the accepted-sources table" in item.item and "Medical Services Professional" in item.item
            for item in record.action_queue
        ), "batch {}".format(batch_number)


def test_app_2026_036_experience_withholds_resolution_only_while_unmatched():
    # Real case: ENT-3602/APP-2026-036. Revision 2 (applications.csv, revision_reason) changes
    # the declared employer from "Willowmere Health Cooperative" to "Silverbeck Physicians
    # Group" (a practice acquisition). The only reply on file at that point, VR-3602
    # (verification-replies.csv), still confirms the pre-acquisition name; a fresh confirmation
    # from Silverbeck, VR-3604, only arrives in batch 3. So: resolved in batch 1 (revision 1's
    # declared employer matches VR-3602 exactly), outstanding in batch 2 (revision 2's employer
    # doesn't match any reply on file yet), resolved again in batch 3 (VR-3604 matches).
    records_b1 = _run_through(1)
    assert records_b1["APP-2026-036"].elements["experience"] == "resolved"

    records_b2 = _run_through(2)
    assert records_b2["APP-2026-036"].elements["experience"] == "outstanding"
    assert records_b2["APP-2026-036"].status == "in-verification"

    records_b3 = _run_through(3)
    assert records_b3["APP-2026-036"].elements["experience"] == "resolved"
    assert records_b3["APP-2026-036"].status == "approved-not-yet-effective"
