# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for least-squares calibration input validation."""

from __future__ import annotations

import numpy as np
import pytest

from station_calibration.calibration.fit import calibrate_camera


def _arrays(n_points: int = 20) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    robot_positions = np.column_stack(
        [
            np.linspace(0.0, 10.0, n_points),
            np.linspace(0.0, 5.0, n_points),
            np.linspace(0.0, 4.0, n_points),
        ]
    )
    image_center_points = np.column_stack(
        [
            np.linspace(400.0, 600.0, n_points),
            np.linspace(300.0, 500.0, n_points),
        ]
    )
    return (
        robot_positions,
        image_center_points,
        np.full(n_points, 10.0),
        np.full(n_points, 1.0),
    )


def test_calibrate_camera_rejects_non_2d_robot_positions() -> None:
    _, image_center_points, radii, sigmas = _arrays()

    with pytest.raises(ValueError, match="robot_positions"):
        calibrate_camera(
            np.zeros(20),
            image_center_points,
            radii,
            sigmas,
        )


def test_calibrate_camera_rejects_non_2d_image_points() -> None:
    robot_positions, _, radii, sigmas = _arrays()

    with pytest.raises(ValueError, match="image_center_points"):
        calibrate_camera(
            robot_positions,
            np.zeros(20),
            radii,
            sigmas,
        )


def test_calibrate_camera_rejects_mismatched_lengths() -> None:
    robot_positions, image_center_points, radii, sigmas = _arrays()

    with pytest.raises(ValueError, match="same number of entries"):
        calibrate_camera(
            robot_positions,
            image_center_points[:-1],
            radii,
            sigmas,
        )


def test_calibrate_camera_rejects_too_few_measurements() -> None:
    robot_positions, image_center_points, radii, sigmas = _arrays(10)

    with pytest.raises(ValueError, match="At least 15"):
        calibrate_camera(
            robot_positions,
            image_center_points,
            radii,
            sigmas,
            n_distortion_coefs=5,
        )


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan")])
def test_calibrate_camera_rejects_invalid_loss_f_scale(value: float) -> None:
    robot_positions, image_center_points, radii, sigmas = _arrays()

    with pytest.raises(ValueError, match="loss_f_scale"):
        calibrate_camera(
            robot_positions,
            image_center_points,
            radii,
            sigmas,
            loss_f_scale=value,
        )


def test_calibrate_camera_accepts_center_covariances() -> None:
    robot_positions, image_center_points, radii, sigmas = _arrays()
    covariance = np.tile(
        np.diag([1e-4, 1e-4]),
        (len(robot_positions), 1, 1),
    )

    result = calibrate_camera(
        robot_positions,
        image_center_points,
        radii,
        sigmas,
        center_covariances=covariance,
    )

    assert np.all(np.isfinite(result.x))
    assert result.fun.size == 2 * len(robot_positions)
    assert result.raw_fun.size == 2 * len(robot_positions)
    assert np.all(np.isfinite(result.raw_fun))


def test_calibrate_camera_rejects_invalid_center_covariances() -> None:
    robot_positions, image_center_points, radii, sigmas = _arrays()

    with pytest.raises(ValueError, match="center_covariances"):
        calibrate_camera(
            robot_positions,
            image_center_points,
            radii,
            sigmas,
            center_covariances=np.zeros((len(robot_positions), 2)),
        )

    indefinite = np.tile(
        np.array([[1.0, 0.0], [0.0, -1.0]]),
        (len(robot_positions), 1, 1),
    )
    with pytest.raises(ValueError, match="positive semidefinite"):
        calibrate_camera(
            robot_positions,
            image_center_points,
            radii,
            sigmas,
            center_covariances=indefinite,
        )
