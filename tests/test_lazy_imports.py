# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for optional heavy imports."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "module",
    [
        "station_calibration",
        "station_calibration.cli",
        "station_calibration.plots",
    ],
)
def test_import_does_not_load_matplotlib(module: str) -> None:
    code = (
        f"import sys; import {module}; "
        "assert 'matplotlib' not in sys.modules, "
        "sorted(name for name in sys.modules if name.startswith('matplotlib'))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [str(ROOT / "src"), env.get("PYTHONPATH", "")],
        )
    )

    subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
