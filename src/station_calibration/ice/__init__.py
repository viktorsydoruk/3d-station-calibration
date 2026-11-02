# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Optional ZeroC Ice transport for the calibration service.

Importing this package itself does not require Ice. The generated stubs and the
``zeroc-ice`` runtime are loaded only when a server or client class is requested.
"""

__all__ = [
    "CalibrationIceClient",
    "CalibrationIceServant",
]


def __getattr__(name: str):
    if name == "CalibrationIceServant":
        from .adapter import CalibrationIceServant

        return CalibrationIceServant
    if name == "CalibrationIceClient":
        from .client import CalibrationIceClient

        return CalibrationIceClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
