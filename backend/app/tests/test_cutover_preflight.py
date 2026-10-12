"""
tests/test_cutover_preflight.py (Phase 5)
The go/no-go gate itself: non-strict passes on a sane local checkout,
--strict rejects it (loopback origins, docs on, http URL), and every
reported line carries one of PASS/FAIL/SKIP.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_preflight_local_passes_non_strict():
    proc = subprocess.run(
        [sys.executable, "scripts/cutover_preflight.py"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS] database.tables" in proc.stdout
    assert "[PASS] database.phase2-columns" in proc.stdout
    for line in proc.stdout.splitlines():
        if line.startswith("["):
            assert line.startswith(("[PASS]", "[FAIL]", "[SKIP]")), line


@pytest.mark.asyncio
async def test_preflight_strict_rejects_local():
    """Localhost origins + docs-on + http URL must FAIL the prod gate."""
    proc = subprocess.run(
        [sys.executable, "scripts/cutover_preflight.py", "--strict"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] config.cors" in proc.stdout
