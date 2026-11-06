# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for camera-model parameter packing and projection."""

from __future__ import annotations

import numpy as np
import pytest

from station_calibration.calibration.initialization import make_initial_parameters
from station_calibration.calibration.model import (
    get_calibration,
    params_names,
    project_points,
    residuals,
    unwrap_k_distortion_params,
    unwrap_params,
)


def _parameters(*, fix_cx_cy: bool = False) -> np.ndarray:
    return make_initial_parameters(
        focal_length=1000.0,
        camera_distance=80.0,
        image_size=(1000, 800),
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=5,
        r_initial=np.eye(3),
    )


def test_unwrap_params_free_and_fixed_principal_point() -> None:
    free = unwrap_params(_parameters(), image_size=(1000, 800))
    fixed = unwrap_params(
        _parameters(fix_cx_cy=True),
        image_size=(1000, 800),
        fix_cx_cy=True,
    )

    assert free[:4] == pytest.approx((1000.0, 1000.0, 500.0, 400.0))
    assert fixed[:4] == pytest.approx((1000.0, 1000.0, 500.0, 400.0))
    np.testing.assert_allclose(free[4][:5], 0.0)
    np.testing.assert_allclose(fixed[4][:5], 0.0)
    np.testing.assert_allclose(free[5], 0.0)
    np.testing.assert_allclose(free[6], [0.0, 0.0, 80.0])


def test_unwrap_k_distortion_params_free_and_fixed_principal_point() -> None:
    free = unwrap_k_distortion_params(_parameters(), n_distortion_coefs=5)
    fixed = unwrap_k_distortion_params(
        _parameters(fix_cx_cy=True),
        fix_cx_cy=True,
        n_distortion_coefs=5,
    )

    assert free.shape == (14,)
    assert fixed.shape == (14,)
    np.testing.assert_allclose(free[:5], 0.0)
    np.testing.assert_allclose(fixed[:5], 0.0)


def test_params_names_match_parameter_layout() -> None:
    free = params_names(fix_cx_cy=False, n_distortion_coefs=5)
    fixed = params_names(fix_cx_cy=True, n_distortion_coefs=0)

    assert free[:4] == ["fx", "fy", "cx", "cy"]
    assert fixed[:2] == ["fx", "fy"]
    assert len(free) == 15
    assert len(fixed) == 8
    assert free[-1] == "t3"


def test_project_points_and_residuals_round_trip() -> None:
    params = _parameters()
    robot_points = np.array([[0.0, 0.0, 0.0], [10.0, -5.0, 0.0]])

    projected = project_points(params, robot_points)
    error = residuals(params, robot_points, projected)

    assert projected.shape == (2, 2)
    np.testing.assert_allclose(error, 0.0, atol=1e-10)


def test_get_calibration_returns_opencv_matrices() -> None:
    intrinsic, distortion, rvec, extrinsic = get_calibration(_parameters())

    np.testing.assert_allclose(
        intrinsic,
        [[1000.0, 0.0, 500.0], [0.0, 1000.0, 400.0], [0.0, 0.0, 1.0]],
    )
    np.testing.assert_allclose(distortion[:5], 0.0)
    np.testing.assert_allclose(rvec, 0.0, atol=1e-10)
    np.testing.assert_allclose(extrinsic[:3, :3], np.eye(3), atol=1e-10)
    np.testing.assert_allclose(extrinsic[:3, 3], [0.0, 0.0, 80.0])
