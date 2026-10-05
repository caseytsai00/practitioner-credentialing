from __future__ import annotations

import os

from scripts.rules import load_rules

RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "deliverables", "rules.md"
)

EXPECTED = {
    "intake.missing_items_clock_days": 30,
    "intake.unexplained_gap_days": 30,
    "verification.attempt_max_count": 3,
    "verification.attempt_min_spacing_days": 21,
    "references.required_count": 2,
    "references.staleness_years": 2,
    "appointment.cycle_years": 2,
    "intake.current_criteria_version": "LARK-PRIV-2026.1",
}


def test_deliverables_rules_file_has_every_expected_id_and_value():
    rules = load_rules(RULES_PATH)
    for rule_id, expected_value in EXPECTED.items():
        assert rule_id in rules, "missing rule id: {}".format(rule_id)
        assert rules[rule_id] == expected_value, "{} = {}, expected {}".format(
            rule_id, rules[rule_id], expected_value
        )
    assert len(rules) == len(EXPECTED), "unexpected extra or missing rule ids: {}".format(
        sorted(rules.keys())
    )
