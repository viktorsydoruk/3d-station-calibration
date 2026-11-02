# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Make the ``slice2py`` output importable.

``slice2py`` emits top-level packages (``Phenoseeder``, ``Phyto``, and
``CommonPhenoseeder``) with absolute imports. The generated files live below the
optional Ice package, so the transport modules put that directory on
``sys.path`` before importing them. This keeps the generated files unchanged and
avoids requiring a custom import hook.
"""

from __future__ import annotations

from pathlib import Path
import sys

__all__ = ["GENERATED_DIR", "ensure_generated_on_path"]

GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def ensure_generated_on_path() -> Path:
    """Add the generated-stub directory to ``sys.path`` once."""
    path = str(GENERATED_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return GENERATED_DIR
