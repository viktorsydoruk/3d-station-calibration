# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for optional debug-image rendering."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from station_calibration.vision.debug import _store_debug_image, debug_images_storing


def test_debug_image_writes_when_radius_is_missing(tmp_path: Path) -> None:
    image = np.zeros((30, 40, 3), dtype=np.uint8)
    target = tmp_path / "nested" / "debug.png"

    debug_images_storing(target, image, x_c_pos=10.0, y_c_pos=12.0)

    assert target.exists()
    assert cv2.imread(str(target)) is not None


def test_debug_image_skips_nonfinite_overlay(tmp_path: Path) -> None:
    image = np.zeros((30, 40, 3), dtype=np.uint8)
    target = tmp_path / "debug.png"

    debug_images_storing(
        target,
        image,
        x_c_pos=np.nan,
        y_c_pos=12.0,
        radius=5.0,
    )

    written = cv2.imread(str(target))
    assert written is not None
    assert np.count_nonzero(written) == 0


def test_store_debug_image_skips_missing_destination() -> None:
    image = np.zeros((10, 10, 3), dtype=np.uint8)

    _store_debug_image(None, image, x_c_pos=1.0, y_c_pos=1.0, radius=2.0)


def test_debug_image_draws_finite_sphere_overlay(tmp_path: Path) -> None:
    image = np.zeros((40, 50, 3), dtype=np.uint8)
    target = tmp_path / "overlay.png"

    debug_images_storing(
        target,
        image,
        x_c_pos=20.0,
        y_c_pos=20.0,
        radius=5.0,
    )

    written = cv2.imread(str(target))
    assert written is not None
    assert np.count_nonzero(written) > 0
