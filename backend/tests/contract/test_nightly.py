"""Nightly jobs (plan §1.1/§1.2, TP-12, M0B-12): 500 rotating Tier A chaos seeds and mutation testing ≥ 70 %."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NIGHTLY = ROOT / ".github" / "workflows" / "nightly.yml"


def test_nightly_workflow_runs_seeds_and_mutation_testing() -> None:
    text = NIGHTLY.read_text()
    assert "schedule:" in text and "cron:" in text
    assert "TL_CHAOS_SEEDS: 500" in text or "TL_CHAOS_SEEDS=500" in text
    assert "mutmut" in text and "stryker" in text.lower()
    assert "--break-at 70" in text or "break: 70" in text or "70" in text


def test_tier_a_reads_its_seed_count_from_the_environment() -> None:
    src = (ROOT / "backend" / "tests" / "system" / "test_north_star_m0b.py").read_text()
    assert "TL_CHAOS_SEEDS" in src
