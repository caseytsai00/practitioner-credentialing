from __future__ import annotations

import scripts


def test_scripts_package_is_importable():
    assert scripts.__doc__ == "Practitioner credentialing Skill implementation."
