# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for robot-home and nozzle geometry."""

from __future__ import annotations

import numpy as np

from station_calibration import (
    find_robot_home_pos_shift,
    get_nozzle_end_home_position,
)


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


def test_nozzle_end_home_position_returns_geometry_and_debug_data() -> None:
    n_points = 24
    z_positions = np.linspace(0.0, 80.0, n_points)
    robot_positions = np.column_stack(
        [
            np.linspace(-40.0, 40.0, n_points),
            np.linspace(-20.0, 20.0, n_points),
            z_positions,
        ]
    )
    image_center_points = np.column_stack(
        [
            1200.0 + 0.2 * robot_positions[:, 0],
            1000.0 + 0.3 * robot_positions[:, 1],
        ]
    )
    intrinsic_matrix = np.array(
        [
            [2000.0, 0.0, 1224.0],
            [0.0, 2000.0, 1024.0],
            [0.0, 0.0, 1.0],
        ]
    )
    sphere_home_position = np.array([10.0, 20.0, 30.0])

    nozzle, sphere_diameter, debug_info = get_nozzle_end_home_position(
        sphere_home_position=sphere_home_position,
        robot_positions=robot_positions,
        image_center_points=image_center_points,
        intrinsic_matrix=intrinsic_matrix,
        extrinsic_matrix=np.eye(4),
        distortion=np.zeros(5),
        sigmas=np.ones(n_points),
        radii=np.full(n_points, 100.0),
        all_directions=np.ones(n_points),
    )

    assert nozzle.shape == (3,)
    assert np.all(np.isfinite(nozzle))
    assert sphere_diameter > 0.0
    assert set(debug_info) == {
        "scaling_visualization",
        "n_sigma_estimation",
        "sphere_radius_estimation",
        "sphere_radius_vs_depth",
    }
    scaling = debug_info["scaling_visualization"]
    assert scaling["z_pos"].shape == scaling["scale"].shape
    assert scaling["z_pos"].size > 3
