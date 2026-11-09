# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-observation covariance whitening."""

from __future__ import annotations

import numpy as np
import pytest

from station_calibration.calibration.weights import (
    center_whitening_matrices,
    match_whitening_scale,
    whiten_residuals,
)


def _robust_scale(values: np.ndarray) -> float:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    median = float(np.median(flat))
    return 1.4826 * float(np.median(np.abs(flat - median)))


def test_whitening_is_inverse_square_root_of_covariance() -> None:
    covariance = np.array(
        [
            [[4.0, 0.0], [0.0, 9.0]],
            [[1.0, 0.2], [0.2, 1.0]],
        ]
    )

    whitening = center_whitening_matrices(covariance)

    for matrix, covariance_i in zip(whitening, covariance):
        np.testing.assert_allclose(
            matrix @ covariance_i @ matrix.T,
            np.eye(2),
            atol=1e-12,
        )


def test_whitening_regularises_singular_covariances() -> None:
    covariance = np.zeros((2, 2, 2), dtype=np.float64)

    whitening = center_whitening_matrices(covariance)

    assert np.all(np.isfinite(whitening))
    assert np.allclose(whitening, np.eye(2) / np.sqrt(1e-6))


def test_whitening_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="shape"):
        center_whitening_matrices(np.zeros((2, 3)))

    with pytest.raises(ValueError, match="finite"):
        center_whitening_matrices(np.full((1, 2, 2), np.nan))

    with pytest.raises(ValueError, match="relative_floor"):
        center_whitening_matrices(np.eye(2)[None, :, :], relative_floor=0.0)


def test_whiten_residuals_applies_matrix_per_observation() -> None:
    residuals = np.array([[1.0, 2.0], [3.0, 4.0]])
    whitening = np.array(
        [
            [[2.0, 0.0], [0.0, 4.0]],
            [[1.0, 0.0], [0.0, 1.0]],
        ]
    )

    whitened = whiten_residuals(residuals, whitening)

    np.testing.assert_allclose(
        whitened,
        np.array([[2.0, 8.0], [3.0, 4.0]]),
    )


def test_match_whitening_scale_preserves_raw_robust_scale() -> None:
    raw = np.array([[1.0, -2.0], [3.0, -4.0], [5.0, -6.0]])
    whitening = np.tile(np.eye(2) * 10.0, (len(raw), 1, 1))

    matched = match_whitening_scale(whitening, raw.reshape(-1))
    white = whiten_residuals(raw, matched).reshape(-1)

    assert _robust_scale(white) == pytest.approx(
        _robust_scale(raw.reshape(-1)),
        rel=1e-12,
    )


def test_match_whitening_scale_handles_degenerate_raw_scale() -> None:
    raw = np.zeros((3, 2), dtype=np.float64)
    whitening = np.tile(np.eye(2), (3, 1, 1))

    matched = match_whitening_scale(whitening, raw.reshape(-1))

    np.testing.assert_allclose(matched, whitening)


def test_global_covariance_scale_is_absorbed_by_whitening_scale() -> None:
    covariance = np.tile(
        np.array([[4.0, 0.5], [0.5, 9.0]]),
        (4, 1, 1),
    )
    raw = np.array(
        [
            [1.0, -2.0],
            [3.0, -4.0],
            [5.0, -6.0],
            [7.0, -8.0],
        ]
    )

    first = match_whitening_scale(
        center_whitening_matrices(covariance),
        raw.reshape(-1),
    )
    second = match_whitening_scale(
        center_whitening_matrices(covariance * 100.0),
        raw.reshape(-1),
    )

    np.testing.assert_allclose(first, second, rtol=1e-12, atol=1e-15)
