from __future__ import annotations

import pytest

from scripts.model import (
    ELEMENT_NAMES,
    ActionItem,
    Activation,
    ApplicationRecord,
    Decision,
    MonitoredCondition,
)


def _all_resolved_elements():
    return {name: "resolved" for name in ELEMENT_NAMES}


def test_application_record_to_dict_shape():
    record = ApplicationRecord(
        application_id="APP-2026-001",
        revision=1,
        status="active",
        elements=_all_resolved_elements(),
        packet_presentable=True,
        decisions=[Decision(decision_id="MEC-2026-011", admitted=True, reason=None)],
        approval_decision_id="GB-2026-011",
        activation=Activation(
            active_at_export=True,
            effective_date="2026-04-01",
            cycle_end="2028-04-01",
            privileges=["PRIV-FM"],
        ),
        monitored_conditions=[MonitoredCondition(condition="Annual CME due", due="2027-04-01")],
        action_queue=[ActionItem(item="Notify committee", owner="Clinical Director", due=None)],
    )

    data = record.to_dict()

    assert data["application_id"] == "APP-2026-001"
    assert data["elements"] == _all_resolved_elements()
    assert data["decisions"] == [
        {"decision_id": "MEC-2026-011", "admitted": True, "reason": None}
    ]
    assert data["activation"]["cycle_end"] == "2028-04-01"
    assert data["monitored_conditions"] == [
        {"condition": "Annual CME due", "due": "2027-04-01"}
    ]
    assert data["action_queue"] == [
        {"item": "Notify committee", "owner": "Clinical Director", "due": None}
    ]


def test_application_record_rejects_bad_status():
    record = ApplicationRecord(
        application_id="APP-2026-002",
        revision=1,
        status="not-a-real-status",
        elements=_all_resolved_elements(),
        packet_presentable=False,
    )
    with pytest.raises(AssertionError):
        record.to_dict()


def test_application_record_requires_all_six_elements():
    record = ApplicationRecord(
        application_id="APP-2026-003",
        revision=1,
        status="in-verification",
        elements={"licensure": "resolved"},
        packet_presentable=False,
    )
    with pytest.raises(AssertionError):
        record.to_dict()


def test_application_record_with_no_activation_or_decisions_serializes_nulls():
    record = ApplicationRecord(
        application_id="APP-2026-004",
        revision=1,
        status="in-verification",
        elements=_all_resolved_elements(),
        packet_presentable=False,
    )
    data = record.to_dict()
    assert data["decisions"] == []
    assert data["approval_decision_id"] is None
    assert data["activation"] is None
    assert data["monitored_conditions"] == []
    assert data["action_queue"] == []
