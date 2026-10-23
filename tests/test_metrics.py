# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for numerical diagnostics and initial rotation handling."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from station_calibration import (
    calculate_RMSE,
    calculate_errors,
    check_distortion_monotonicity,
)
from station_calibration.calibration.initialization import (
    estimate_r_initial,
    make_initial_parameters,
)


def _result(fun: list[float], jac: np.ndarray) -> OptimizeResult:
    return OptimizeResult(
        x=np.zeros(jac.shape[1]),
        fun=np.asarray(fun, dtype=np.float64),
        jac=np.asarray(jac, dtype=np.float64),
        success=True,
        cost=0.0,
        message="test",
    )


def _intrinsic(focal_length: float = 1000.0) -> np.ndarray:
    return np.array(
        [
            [focal_length, 0.0, 500.0],
            [0.0, focal_length, 500.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def test_calculate_errors_matches_classical_covariance() -> None:
    rng = np.random.default_rng(0)
    jacobian = rng.normal(size=(20, 5))
    residuals = rng.normal(size=20)
    result = _result(residuals, jacobian)

    sigma2 = np.sum(residuals ** 2) / (len(residuals) - jacobian.shape[1])
    expected = np.sqrt(np.diag(np.linalg.inv(jacobian.T @ jacobian) * sigma2))

    np.testing.assert_allclose(
        calculate_errors(result), expected, rtol=1e-9, atol=1e-12
    )


def test_calculate_errors_handles_rank_deficient_jacobian() -> None:
    jacobian = np.array(
        [
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
        ]
    )
    result = _result([1.0, -1.0, 1.0, -1.0], jacobian)

    errors = calculate_errors(result)

    assert errors.shape == (2,)
    assert np.all(np.isfinite(errors))


def test_calculate_errors_returns_nan_without_degrees_of_freedom() -> None:
    result = _result([1.0, 2.0], np.eye(2))

    errors = calculate_errors(result)

    assert np.all(np.isnan(errors))


def test_calculate_errors_rejects_mismatched_jacobian() -> None:
    with pytest.raises(ValueError, match="one row per residual"):
        calculate_errors(_result([1.0, 2.0], np.eye(3)))


def test_calculate_RMSE_plain_and_standardized() -> None:
    result = _result([3.0, 4.0], np.ones((2, 1)))

    assert calculate_RMSE(result, standardized=False) == pytest.approx(
        np.sqrt(12.5)
    )
    assert calculate_RMSE(result, standardized=True) == pytest.approx(5.0)
    assert calculate_RMSE(result) == pytest.approx(5.0)


def test_calculate_RMSE_standardized_is_nan_without_degrees_of_freedom() -> None:
    result = _result([3.0, 4.0], np.eye(2))

    assert np.isnan(calculate_RMSE(result, standardized=True))
    assert calculate_RMSE(result, standardized=False) == pytest.approx(
        np.sqrt(12.5)
    )


def test_calculate_RMSE_returns_nan_for_nonfinite_residuals() -> None:
    result = _result([1.0, np.nan], np.ones((2, 1)))

    assert np.isnan(calculate_RMSE(result, standardized=False))
    assert np.isnan(calculate_RMSE(result, standardized=True))


def test_distortion_monotonicity_accepts_identity_and_decreasing_models() -> None:
    intrinsic = _intrinsic()

    assert check_distortion_monotonicity(np.zeros(14), intrinsic, (1000, 1000))

    decreasing = np.zeros(14)
    decreasing[0] = -0.5
    assert check_distortion_monotonicity(decreasing, intrinsic, (1000, 1000))


@pytest.mark.parametrize("coefficient_index", [5, 6, 7])
def test_distortion_monotonicity_checks_higher_radial_terms(
    coefficient_index: int,
) -> None:
    distortion = np.zeros(14)
    distortion[0] = 1.0
    distortion[coefficient_index] = -100.0

    assert not check_distortion_monotonicity(
        distortion, _intrinsic(), (1000, 1000)
    )


def test_distortion_monotonicity_rejects_negative_radial_scale() -> None:
    distortion = np.zeros(14)
    distortion[0] = -100.0

    assert not check_distortion_monotonicity(
        distortion, _intrinsic(), (1000, 1000)
    )


def test_distortion_monotonicity_rejects_invalid_inputs() -> None:
    distortion = np.zeros(14)
    distortion[0] = np.nan

    assert not check_distortion_monotonicity(
        distortion, _intrinsic(), (1000, 1000)
    )
    assert not check_distortion_monotonicity(
        np.zeros(14), _intrinsic(focal_length=0.0), (1000, 1000)
    )
    assert not check_distortion_monotonicity(
        np.zeros(14), _intrinsic(), (-1, 1000)
    )


def _assert_proper_rotation(matrix: np.ndarray) -> None:
    np.testing.assert_allclose(matrix.T @ matrix, np.eye(3), atol=1e-12)
    assert np.linalg.det(matrix) == pytest.approx(1.0, abs=1e-12)


def test_estimate_r_initial_returns_proper_rotation() -> None:
    rng = np.random.default_rng(1)
    n_points = 30
    robot_positions = rng.normal(size=(n_points, 3))
    image_center_points = rng.normal(size=(n_points, 2)) * 100.0 + 500.0
    radii = rng.uniform(10.0, 15.0, n_points)
    sigmas = rng.uniform(0.5, 2.0, n_points)

    rotation = estimate_r_initial(
        robot_positions, image_center_points, radii, sigmas
    )

    _assert_proper_rotation(rotation)


def test_estimate_r_initial_falls_back_for_degenerate_data() -> None:
    rotation = estimate_r_initial(
        np.ones((5, 3)),
        np.ones((5, 2)),
        np.ones(5),
        np.ones(5),
    )

    np.testing.assert_allclose(rotation, np.eye(3))


def test_make_initial_parameters_orthonormalizes_rotation() -> None:
    params = make_initial_parameters(
        focal_length=1000.0,
        camera_distance=80.0,
        image_size=(1000, 1000),
        fix_cx_cy=True,
        n_distortion_coefs=0,
        r_initial=np.diag([1.0, 2.0, 1.0]),
    )

    rotation, _ = cv2.Rodrigues(params[2:5])

    _assert_proper_rotation(rotation)
