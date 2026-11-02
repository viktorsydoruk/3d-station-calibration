# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Regenerate the Python Ice stubs from the production contracts."""

from __future__ import annotations

import shutil
from pathlib import Path
import subprocess
import sys

__all__ = ["main"]

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "src" / "station_calibration" / "ice" / "generated"
CONTRACT = ROOT / "ice" / "CalibrationPhenoseederIcing.ice"
SHARED_INCLUDES = (
    ROOT / "ice" / "CommonPhenoseeder.ice",
    ROOT / "ice" / "PhytoCommon.ice",
)
GENERATED_PACKAGES = ("Phenoseeder", "Phyto", "CommonPhenoseeder")


def _find_slice2py() -> str:
    executable = "slice2py.exe" if sys.platform == "win32" else "slice2py"
    sibling = Path(sys.executable).with_name(executable)
    if sibling.is_file():
        return str(sibling)

    found = shutil.which("slice2py")
    if found is not None:
        return found

    raise SystemExit(
        "slice2py was not found. Install the optional Ice extra and run "
        "this script from the project virtual environment."
    )


def main() -> None:
    slice2py = _find_slice2py()

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    # slice2py does not delete stubs whose Slice definition has disappeared.
    # Remove the generated packages first so the tree always matches the .ice
    # files name for name.
    for package in GENERATED_PACKAGES:
        shutil.rmtree(GENERATED_DIR / package, ignore_errors=True)

    command = [
        slice2py,
        "-I",
        str(ROOT / "ice"),
        "--output-dir",
        str(GENERATED_DIR),
        *[str(path) for path in SHARED_INCLUDES],
        str(CONTRACT),
    ]
    print("Running:", " ".join(command))
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
    sys.exit(0)
