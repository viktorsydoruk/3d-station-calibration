# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Compatibility entry point for ``python -m`` from the project root."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from station_calibration.cli import run_cli  # noqa: E402

if __name__ == "__main__":
    run_cli()
