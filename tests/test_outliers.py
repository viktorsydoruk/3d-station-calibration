# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the chi-square outlier diagnostics."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import OptimizeResult
from scipy.stats import chi2

from station_calibration.calibration.outliers import (
    calculate_outlier_scores,
    chi_square_threshold,
    is_spatially_clustered,
)


def _result(fun: np.ndarray, jac: np.ndarray | None = None) -> OptimizeResult:
    data = {"fun": np.asarray(fun, dtype=np.float64)}
    if jac is not None:
        data["jac"] = np.asarray(jac, dtype=np.float64)
    return OptimizeResult(**data)


def test_chi_square_threshold_matches_scipy() -> None:
    assert chi_square_threshold(0.999) == pytest.approx(
        chi2.ppf(0.999, df=2)
    )
    assert chi_square_threshold(0.5) == pytest.approx(chi2.ppf(0.5, df=2))


@pytest.mark.parametrize("value", [0.0, 1.0, -0.1, 1.1, np.nan, np.inf])
def test_chi_square_threshold_rejects_invalid_confidence(value: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        chi_square_threshold(value)


def test_outlier_scores_flag_a_single_gross_residual() -> None:
    rng = np.random.default_rng(0)
    n_points = 100
    n_parameters = 5
    jacobian = rng.normal(size=(2 * n_points, n_parameters))
    residuals = rng.normal(size=2 * n_points)
    outlier = 17
    residuals[2 * outlier] += 25.0

    scores = calculate_outlier_scores(_result(residuals, jacobian))

    threshold = chi_square_threshold(0.999)
    assert scores[outlier] > threshold
    assert int(np.nanargmax(scores)) == outlier
    assert np.count_nonzero(scores > threshold) <= 2


def test_outlier_scores_do_not_flag_gaussian_noise() -> None:
    rng = np.random.default_rng(1)
    n_points = 200
    jacobian = rng.normal(size=(2 * n_points, 4))
    residuals = rng.normal(size=2 * n_points)

    scores = calculate_outlier_scores(_result(residuals, jacobian), robust=False)

    assert np.all(np.isfinite(scores))
    assert np.count_nonzero(scores > chi_square_threshold(0.999)) <= 2


def test_outlier_scores_apply_leverage_correction() -> None:
    n_points = 50
    jacobian = np.zeros((2 * n_points, 2))
    jacobian[0:2] = 10.0 * np.eye(2)
    for index in range(1, n_points):
        jacobian[2 * index:2 * index + 2] = np.eye(2)

    residuals = np.full(2 * n_points, 0.01)
    residuals[0:2] = [3.0, 3.0]
    residuals[2:4] = [3.0, 3.0]

    scores = calculate_outlier_scores(_result(residuals, jacobian), robust=False)

    # The first point has much higher leverage, so its residual covariance is
    # smaller and the same raw residual is *more* surprising.  The leverage
    # correction must therefore give it the larger Mahalanobis score.
    assert scores[0] > scores[1]


def test_outlier_scores_fall_back_without_jacobian() -> None:
    residuals = np.array([0.1, -0.2, 0.3, -0.4, 10.0, 0.1])

    scores = calculate_outlier_scores(_result(residuals))

    assert np.all(np.isfinite(scores))
    assert int(np.argmax(scores)) == 2


def test_outlier_scores_return_nan_when_degrees_of_freedom_are_not_positive() -> None:
    residuals = np.array([0.1, -0.2, 0.3, -0.4])
    jacobian = np.ones((4, 5))

    scores = calculate_outlier_scores(_result(residuals, jacobian))

    assert scores.shape == (2,)
    assert np.all(np.isnan(scores))


def test_outlier_scores_return_nan_for_invalid_residuals() -> None:
    odd = calculate_outlier_scores(_result(np.zeros(5)))
    assert odd.shape == (2,)
    assert np.all(np.isnan(odd))

    nonfinite = calculate_outlier_scores(_result([0.0, 1.0, np.nan, 2.0]))
    assert nonfinite.shape == (2,)
    assert np.all(np.isnan(nonfinite))

    zero = calculate_outlier_scores(_result(np.zeros(8)))
    assert zero.shape == (4,)
    assert np.all(np.isnan(zero))


def test_outlier_scores_ignore_malformed_jacobian() -> None:
    residuals = np.array([0.1, -0.2, 0.3, -0.4, 10.0, 0.1])
    malformed = OptimizeResult(fun=residuals, jac=np.ones((3, 3)))

    scores = calculate_outlier_scores(malformed)

    assert np.all(np.isfinite(scores))


def _grid_points(side: int = 10) -> np.ndarray:
    x, y = np.meshgrid(np.arange(side), np.arange(side))
    return np.column_stack([x.ravel(), y.ravel(), np.zeros(side * side)])


def test_spatial_cluster_detects_a_compact_block_on_a_grid() -> None:
    points = _grid_points()
    block = np.array([0, 1, 10, 11])

    assert is_spatially_clustered(points, block)


def test_spatial_cluster_accepts_scattered_points() -> None:
    points = _grid_points()
    scattered = np.array([0, 33, 66, 99])

    assert not is_spatially_clustered(points, scattered)


def test_spatial_cluster_requires_at_least_three_candidates() -> None:
    points = _grid_points()

    assert not is_spatially_clustered(points, np.array([0, 1]))
    assert not is_spatially_clustered(points, np.array([0]))


def test_spatial_cluster_rejects_all_points_and_invalid_inputs() -> None:
    points = _grid_points()

    assert not is_spatially_clustered(points, np.arange(len(points)))

    with pytest.raises(ValueError, match="percentile"):
        is_spatially_clustered(points, np.array([0, 1, 2]), percentile=100.0)
    with pytest.raises(ValueError, match="n_permutations"):
        is_spatially_clustered(points, np.array([0, 1, 2]), n_permutations=0)
    with pytest.raises(IndexError, match="out-of-range"):
        is_spatially_clustered(points, np.array([0, 1, 1000]))


def test_spatial_cluster_handles_nonfinite_points_and_duplicates() -> None:
    points = _grid_points()
    points[0, 0] = np.nan

    assert not is_spatially_clustered(points, np.array([0, 1, 2]))

    duplicates = np.zeros((5, 3))
    assert is_spatially_clustered(duplicates, np.array([0, 1, 2]))
