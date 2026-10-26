"""North-star contract (plan §1.1, M0B-12).

`contracts/north_star.yaml` lists the north-star sub-steps (requirements README), each tagged with the milestone
that delivers it and how it is driven: `api` (Tier A, pytest `@pytest.mark.north_star("<id>")` under
`backend/tests/system`) or `ui` (Tier B, Playwright test title containing `@ns:<id>` under `e2e/`).

Rules enforced here:
- every step is tagged (known milestone, non-empty drivers from {api, ui}) and ids are unique;
- every step of the current or an earlier milestone has a test for each of its drivers (kickoff writes them first,
  as strict expected failures, so a step passing early fails the build — TP-7);
- no test is tagged with an unknown step id.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "contracts" / "north_star.yaml"
MILESTONES = ["M0b", "M1", "M2", "M3", "M3.5", "M4a", "M4b", "M5", "M6", "M7", "M8", "M9"]
API_TAG = re.compile(r"""north_star\(\s*["']([^"']+)["']\s*\)""")
UI_TAG = re.compile(r"@ns:([A-Za-z0-9_.\-]+)")


def _contract() -> dict[str, Any]:
    doc = yaml.safe_load(CONTRACT.read_text())
    assert isinstance(doc, dict), "north_star.yaml must be a mapping"
    return doc


def _tags(root: Path, glob: str, pattern: re.Pattern[str]) -> set[str]:
    return {m for f in root.glob(glob) for m in pattern.findall(f.read_text())}


def api_tags() -> set[str]:
    return _tags(ROOT / "backend" / "tests" / "system", "**/*.py", API_TAG)


def ui_tags() -> set[str]:
    return _tags(ROOT / "e2e", "*.spec.ts", UI_TAG)


def test_every_step_is_tagged_with_milestone_and_driver() -> None:
    doc = _contract()
    assert doc.get("current_milestone") in MILESTONES
    steps = doc.get("steps")
    assert isinstance(steps, list) and steps
    ids = [s.get("id") for s in steps]
    assert len(ids) == len(set(ids)), "duplicate step ids"
    for s in steps:
        assert isinstance(s.get("id"), str) and s["id"], s
        assert s.get("milestone") in MILESTONES, f"untagged or unknown milestone: {s}"
        drivers = s.get("drivers")
        assert isinstance(drivers, list) and drivers and set(drivers) <= {"api", "ui"}, f"bad drivers: {s}"
        assert isinstance(s.get("what"), str) and s["what"], f"step needs a description: {s}"


def test_steps_up_to_the_current_milestone_have_tests_for_each_driver() -> None:
    doc = _contract()
    current = MILESTONES.index(doc["current_milestone"])
    have = {"api": api_tags(), "ui": ui_tags()}
    missing = [
        f"{s['id']} ({d})"
        for s in doc["steps"]
        if MILESTONES.index(s["milestone"]) <= current
        for d in s["drivers"]
        if s["id"] not in have[d]
    ]
    assert not missing, f"north-star steps without a test: {missing}"


def test_no_test_is_tagged_with_an_unknown_step() -> None:
    known = {s["id"] for s in _contract()["steps"]}
    unknown = (api_tags() | ui_tags()) - known
    assert not unknown, f"tests tagged with unknown north-star steps: {sorted(unknown)}"
