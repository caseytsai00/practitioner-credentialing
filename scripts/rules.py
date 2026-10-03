from __future__ import annotations

import re
from typing import Dict

import yaml

_YAML_BLOCK_RE = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)


def load_rules(path: str) -> Dict[str, object]:
    with open(path, encoding="utf-8") as f:
        text = f.read()

    rules: Dict[str, object] = {}
    for block in _YAML_BLOCK_RE.findall(text):
        data = yaml.safe_load(block)
        if isinstance(data, dict) and "id" in data and "value" in data:
            rules[data["id"]] = data["value"]
    return rules
