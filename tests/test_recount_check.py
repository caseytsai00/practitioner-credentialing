from __future__ import annotations

import os

from scripts.recount_check import count_admitted_gb_approvals, count_ppq_yes_findings

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_count_ppq_yes_findings_on_real_batch_01():
    counts = count_ppq_yes_findings(os.path.join(REPO_ROOT, "office-exports", "batch-01"))
    # APP-2026-032's high-risk finding disposition (batch-02) concerns PPQ-2 answered Yes --
    # confirm the raw disclosure data backs that up from batch-01's intake.
    assert counts.get("APP-2026-032", 0) >= 1


def test_count_admitted_gb_approvals_on_real_batch_02():
    count = count_admitted_gb_approvals(os.path.join(REPO_ROOT, "office-exports", "batch-02", "decisions"))
    assert count >= 1
