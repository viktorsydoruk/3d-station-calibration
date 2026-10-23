# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Project-root compatibility marker.

The actual library lives in ``src/station_calibration``. This file only keeps
legacy imports from the repository root working during the migration.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from station_calibration import *  # noqa: E402,F401,F403
