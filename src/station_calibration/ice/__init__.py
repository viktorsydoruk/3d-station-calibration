# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Optional ZeroC Ice transport for the calibration service.

Importing this package itself does not require Ice. The generated stubs and the
``zeroc-ice`` runtime are loaded only when a server or client class is requested.
"""

__all__ = [
    "CalibrationIceClient",
    "CalibrationIceServant",
    "DEFAULT_MESSAGE_SIZE_MAX_KB",
]

# Camera frames are sent as raw pixels. A 2048x2448 8-bit frame is about 5 MB,
# which exceeds Ice's 1 MB default incoming-message limit. Keep this comfortably
# above the largest expected frame and use it on both client and server.
DEFAULT_MESSAGE_SIZE_MAX_KB = 65536


def __getattr__(name: str):
    if name == "CalibrationIceServant":
        from .adapter import CalibrationIceServant

        return CalibrationIceServant
    if name == "CalibrationIceClient":
        from .client import CalibrationIceClient

        return CalibrationIceClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
