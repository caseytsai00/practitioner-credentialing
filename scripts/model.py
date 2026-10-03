from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

ELEMENT_NAMES = ["licensure", "experience", "gaps", "education", "certification", "references"]

ELEMENT_STATES = {
    "resolved",
    "outstanding",
    "finding",
    "discrepancy",
    "return-incomplete",
    "routed-to-clinical-director",
    "eligibility-question",
}

APPLICATION_STATUSES = {
    "intake-incomplete",
    "returned-incomplete",
    "ineligible-clock-expired",
    "in-verification",
    "packet-presentable",
    "decision-inadmissible",
    "deferred",
    "denied",
    "approved-not-yet-effective",
    "active",
    "active-with-conditions",
    "withdrawn",
    "discontinued",
}


@dataclass
class Decision:
    decision_id: str
    admitted: bool
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {"decision_id": self.decision_id, "admitted": self.admitted, "reason": self.reason}


@dataclass
class Activation:
    active_at_export: bool
    effective_date: str
    cycle_end: str
    privileges: List[str]

    def to_dict(self) -> dict:
        return {
            "active_at_export": self.active_at_export,
            "effective_date": self.effective_date,
            "cycle_end": self.cycle_end,
            "privileges": list(self.privileges),
        }


@dataclass
class MonitoredCondition:
    condition: str
    due: str

    def to_dict(self) -> dict:
        return {"condition": self.condition, "due": self.due}


@dataclass
class ActionItem:
    item: str
    owner: str
    due: Optional[str] = None

    def to_dict(self) -> dict:
        return {"item": self.item, "owner": self.owner, "due": self.due}


@dataclass
class ApplicationRecord:
    application_id: str
    revision: int
    status: str
    elements: Dict[str, str]
    packet_presentable: bool
    decisions: List[Decision] = field(default_factory=list)
    approval_decision_id: Optional[str] = None
    activation: Optional[Activation] = None
    monitored_conditions: List[MonitoredCondition] = field(default_factory=list)
    action_queue: List[ActionItem] = field(default_factory=list)

    def validate(self) -> None:
        assert self.status in APPLICATION_STATUSES, "bad status: {}".format(self.status)
        assert set(self.elements.keys()) == set(ELEMENT_NAMES), (
            "elements must cover exactly the six verified elements, got {}".format(
                sorted(self.elements.keys())
            )
        )
        for name, state in self.elements.items():
            assert state in ELEMENT_STATES, "bad element state for {}: {}".format(name, state)

    def to_dict(self) -> dict:
        self.validate()
        return {
            "application_id": self.application_id,
            "revision": self.revision,
            "status": self.status,
            "elements": dict(self.elements),
            "packet_presentable": self.packet_presentable,
            "decisions": [d.to_dict() for d in self.decisions],
            "approval_decision_id": self.approval_decision_id,
            "activation": self.activation.to_dict() if self.activation else None,
            "monitored_conditions": [m.to_dict() for m in self.monitored_conditions],
            "action_queue": [a.to_dict() for a in self.action_queue],
        }
