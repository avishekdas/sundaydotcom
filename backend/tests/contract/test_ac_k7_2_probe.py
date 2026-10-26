"""AC-K7-2 is re-proven on dev after every deploy (D-046, M1 close): runner = IP A, the ip-probe λ = IP B."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_e2e_dev_runs_the_two_ip_probe() -> None:
    script = ROOT / "scripts" / "ac-k7-2-probe.sh"
    assert script.is_file() and os.access(script, os.X_OK)
    body = script.read_text()
    for needed in ("tasklane-dev-ip-probe", "clear_counters", "sign_in", "429", "35"):
        assert needed in body, needed
    assert "ac-k7-2-probe.sh" in (ROOT / ".github" / "workflows" / "e2e-dev.yml").read_text()
