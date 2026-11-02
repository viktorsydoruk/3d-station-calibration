# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry point for ``python -m station_calibration``."""

from .cli import run_cli

if __name__ == "__main__":
    run_cli()
