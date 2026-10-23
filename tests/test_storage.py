# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for point-cache storage."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from station_calibration.storage import load_all_points, store_all_points


def test_point_cache_round_trip_preserves_float64(tmp_path: Path) -> None:
    robot_positions = np.array(
        [
            [312.1234567890123, -110.9876543210987, -36.4],
            [318.06, -107.94, -35.44],
        ],
        dtype=np.float64,
    )
    center_points = np.array(
        [
            [331.7058188960392, 629.0855863442323],
            [2045.384785120838, 915.3024372938667],
        ],
        dtype=np.float64,
    )
    radii = np.array([156.41471540876242, 170.65923626094033], dtype=np.float64)
    sigmas = np.array([6.58892138764756, 16.852260747805076], dtype=np.float64)
    image_sizes = np.array([[2048.0, 2448.0], [2048.0, 2448.0]], dtype=np.float64)
    directions = np.array([-1, 1], dtype=np.int8)

    point_file = tmp_path / "all_points.dat"
    store_all_points(
        point_file,
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_sizes,
        directions,
    )

    loaded = load_all_points(point_file)

    for array in loaded[:5]:
        assert array.dtype == np.float64
    assert loaded[5].dtype == np.int8

    np.testing.assert_array_equal(loaded[0], robot_positions)
    np.testing.assert_array_equal(loaded[1], center_points)
    np.testing.assert_array_equal(loaded[2], radii)
    np.testing.assert_array_equal(loaded[3], sigmas)
    np.testing.assert_array_equal(loaded[4], image_sizes)
    np.testing.assert_array_equal(loaded[5], directions)
