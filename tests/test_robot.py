# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for robot-home and nozzle geometry."""

from __future__ import annotations

import numpy as np

from station_calibration import find_robot_home_pos_shift


def test_home_shift_accepts_zero_sigmas() -> None:
    """The sigma offset keeps zero-sigma weights finite."""
    rng = np.random.default_rng(1)
    n_points = 20
    robot_positions = np.column_stack(
        [
            rng.uniform(-50.0, 50.0, n_points),
            rng.uniform(-50.0, 50.0, n_points),
            rng.uniform(-20.0, 20.0, n_points),
        ]
    )
    image_center_points = np.column_stack(
        [
            rng.uniform(800.0, 1600.0, n_points),
            rng.uniform(600.0, 1400.0, n_points),
        ]
    )
    intrinsic_matrix = np.array(
        [
            [2000.0, 0.0, 1224.0],
            [0.0, 2000.0, 1024.0],
            [0.0, 0.0, 1.0],
        ]
    )

    shift = find_robot_home_pos_shift(
        robot_positions,
        image_center_points,
        intrinsic_matrix,
        np.eye(4),
        np.zeros(5),
        np.zeros(n_points),
    )

    assert np.all(np.isfinite(shift))
