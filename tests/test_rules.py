from __future__ import annotations

import os

from scripts.rules import load_rules

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.md")


def test_load_rules_extracts_id_value_pairs():
    rules = load_rules(FIXTURE)
    assert rules["sample.one"] == 30
    assert rules["sample.two"] == 3


def test_load_rules_ignores_blocks_without_an_id():
    rules = load_rules(FIXTURE)
    assert "note" not in rules
    assert len(rules) == 2
