"""Compatibility entry point for the folder calibration workflow.

New code should import :func:`station_calibration.cli.main` directly.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from station_calibration.cli import main  # noqa: E402

__all__ = ["main"]
