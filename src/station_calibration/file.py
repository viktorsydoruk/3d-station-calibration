# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Deprecated compatibility shim for :mod:`station_calibration.storage`."""

__all__ = [
    "load_robot_positions",
    "search_images",
    "store_all_points",
    "load_all_points",
    "store_calibration",
]

from .storage import (
    load_all_points,
    load_robot_positions,
    search_images,
    store_all_points,
    store_calibration,
)
