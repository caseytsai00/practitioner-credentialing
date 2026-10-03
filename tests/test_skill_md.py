from __future__ import annotations

import os

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_skill_md_has_name_and_description_frontmatter():
    with open(os.path.join(REPO_ROOT, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    assert text.startswith("---\n")
    end = text.index("\n---", 4)
    frontmatter = yaml.safe_load(text[4:end])
    assert frontmatter["name"]
    assert len(frontmatter["description"]) > 20


def test_skill_md_names_the_real_entrypoint():
    with open(os.path.join(REPO_ROOT, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    assert "scripts/run_batch.py" in text
    assert "deliverables/rules.md" in text
