"""Runs the TypeScript helper tests for DIDWW concat highlight."""

from __future__ import annotations

import subprocess
from pathlib import Path

HELPER_TEST = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "components"
    / "numbers"
    / "prefixHighlight.test.ts"
)


def test_frontend_prefix_highlight_helper():
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--test", str(HELPER_TEST)],
        cwd=str(HELPER_TEST.parent),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4420 highlights both country and area cells" in result.stderr + result.stdout
    assert "20 highlights only the area prefix" in result.stderr + result.stdout
