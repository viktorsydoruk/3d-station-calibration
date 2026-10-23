# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Deprecated compatibility package.

All implementation now lives in :mod:`station_calibration`. Import from that
package in new code. This package remains as a thin re-export shim so existing
scripts and tests continue to work during the migration.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from station_calibration import *  # noqa: E402,F401,F403
