# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Outlier diagnostics for the 2D reprojection residuals."""

__all__ = [
    "calculate_outlier_scores",
    "chi_square_threshold",
    "is_spatially_clustered",
]

import numpy as np
from scipy.optimize import OptimizeResult
from scipy.stats import chi2


def chi_square_threshold(confidence: float = 0.999) -> float:
    """Return the 2D chi-square threshold for a confidence level.

    A squared Mahalanobis distance of a two-dimensional residual follows a
    chi-square distribution with two degrees of freedom. The default ``0.999``
    therefore flags roughly one point in a thousand.
    """
    confidence = float(confidence)
    if not np.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError(
            f"confidence must be finite and strictly between 0 and 1, got {confidence}"
        )
    return float(chi2.ppf(confidence, df=2))


def _noise_variance(residuals: np.ndarray,
                    jacobian: np.ndarray | None,
                    *,
                    robust: bool) -> float:
    """Estimate the scalar residual variance used by the outlier test."""
    n_residuals = residuals.size
    n_parameters = 0 if jacobian is None else jacobian.shape[1]
    degrees_of_freedom = n_residuals - n_parameters
    if degrees_of_freedom <= 0:
        return float("nan")

    if robust:
        # Median absolute deviation of the pooled residual components. The
        # 1.4826 factor makes the estimate consistent with the standard
        # deviation for Gaussian noise. Fall back to the sum of squares when
        # the median is degenerate (for example, a synthetic all-zero fixture).
        median = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - median)))
        if np.isfinite(mad) and mad > 0.0:
            return float((1.4826 * mad) ** 2)

    sum_squares = float(np.dot(residuals, residuals))
    return sum_squares / degrees_of_freedom


def calculate_outlier_scores(result: OptimizeResult,
                             *,
                             robust: bool = True) -> np.ndarray:
    """Return leverage-corrected squared Mahalanobis distances.

    The fit minimizes a 2D residual vector ``r_i`` per observation. For a
    linear least-squares fit (ordinary or generalized after whitening) the
    residual covariance is approximately

    ``Cov(r) = sigma^2 * (I - H)``,

    with the hat matrix ``H = J (J^T J)^-1 J^T``. The score of point ``i`` is

    ``d_i^2 = r_i^T Cov(r_i)^-1 r_i``,

    which follows a chi-square distribution with two degrees of freedom when the
    model and noise are correct. Points above :func:`chi_square_threshold` are
    statistically inconsistent with the fitted model; they are candidate
    blunders, not ordinary noise.

    The robust scale option estimates ``sigma`` from the median absolute
    deviation, so a few gross outliers do not inflate the covariance and mask
    themselves. The leverage correction still uses the fit Jacobian.

    ``result.jac`` is optional. When it is missing or malformed, the function
    falls back to a diagonal covariance without leverage correction; the fit
    itself always provides it. Non-finite or odd-length residuals return an
    array of ``nan``.
    """
    residuals = np.asarray(result.fun, dtype=np.float64).reshape(-1)
    if residuals.size == 0 or residuals.size % 2 != 0:
        return np.full(residuals.size // 2, np.nan, dtype=np.float64)
    if not np.all(np.isfinite(residuals)):
        return np.full(residuals.size // 2, np.nan, dtype=np.float64)

    residuals_2d = residuals.reshape(-1, 2)
    n_points = len(residuals_2d)

    jacobian = getattr(result, "jac", None)
    if jacobian is not None:
        jacobian = np.asarray(jacobian, dtype=np.float64)
        if (
            jacobian.ndim != 2
            or jacobian.shape[0] != residuals.size
            or not np.all(np.isfinite(jacobian))
        ):
            jacobian = None

    sigma2 = _noise_variance(residuals, jacobian, robust=robust)
    if not np.isfinite(sigma2) or sigma2 <= 0.0:
        return np.full(n_points, np.nan, dtype=np.float64)

    jtj_inv = None
    if jacobian is not None:
        try:
            jtj_inv = np.linalg.pinv(jacobian.T @ jacobian)
        except np.linalg.LinAlgError:
            jtj_inv = None

    scores = np.full(n_points, np.nan, dtype=np.float64)
    ridge = np.finfo(np.float64).eps * max(1.0, sigma2)
    for index in range(n_points):
        covariance = sigma2 * np.eye(2, dtype=np.float64)
        if jacobian is not None and jtj_inv is not None:
            jacobian_i = jacobian[2 * index:2 * index + 2]
            leverage = jacobian_i @ jtj_inv @ jacobian_i.T
            covariance = sigma2 * (np.eye(2, dtype=np.float64) - leverage)

        # Symmetrize and add a tiny ridge so that a degenerate leverage block
        # (a point with no residual degrees of freedom) still yields a finite
        # pseudo-inverse instead of dividing by zero.
        covariance = 0.5 * (covariance + covariance.T)
        covariance += ridge * np.eye(2, dtype=np.float64)
        score = float(
            residuals_2d[index] @ np.linalg.pinv(covariance) @ residuals_2d[index]
        )
        if np.isfinite(score) and score >= 0.0:
            scores[index] = score

    return scores


def _spatial_spread(points: np.ndarray) -> float:
    """Return the RMS distance of points from their centroid."""
    centered = points - np.mean(points, axis=0)
    return float(np.sqrt(np.mean(np.sum(centered ** 2, axis=1))))


def is_spatially_clustered(points: np.ndarray,
                           candidate_indices: np.ndarray,
                           *,
                           percentile: float = 5.0,
                           n_permutations: int = 200,
                           random_state: int = 0) -> bool:
    """Return whether candidate points form a compact spatial cluster.

    A single blunder is usually isolated in the workspace. A group of
    high-score points that are packed into a small region is more likely to
    indicate a systematic robot or camera-model error. Removing such a group
    would bias the calibration and reduce coverage, so the pipeline keeps it
    and reports the condition instead.

    The test compares the RMS spread of the candidates with the spread of
    random subsets of the same size drawn from the active set. A uniform robot
    raster is handled correctly: a contiguous block has a much smaller spread
    than a random block, even though their nearest-neighbour distances are
    identical. The candidate is a cluster when its spread is below the
    ``percentile`` of the permutation distribution.
    """
    if not 0.0 < percentile < 100.0:
        raise ValueError(f"percentile must be in (0, 100), got {percentile}")
    if n_permutations < 1:
        raise ValueError(f"n_permutations must be positive, got {n_permutations}")

    points = np.asarray(points, dtype=np.float64)
    candidate_indices = np.asarray(candidate_indices, dtype=np.intp).reshape(-1)

    if points.ndim != 2 or len(candidate_indices) < 3:
        return False
    if not np.all(np.isfinite(points)):
        return False
    if np.any(candidate_indices < 0) or np.any(candidate_indices >= len(points)):
        raise IndexError("candidate_indices contains an out-of-range index")
    if len(points) < 4 or len(candidate_indices) >= len(points):
        return False

    candidate_points = points[candidate_indices]

    candidate_spread = _spatial_spread(candidate_points)
    if candidate_spread == 0.0:
        return True

    rng = np.random.default_rng(random_state)
    sample_size = len(candidate_indices)
    null_spreads = np.empty(n_permutations, dtype=np.float64)
    for index in range(n_permutations):
        sample = rng.choice(len(points), size=sample_size, replace=False)
        null_spreads[index] = _spatial_spread(points[sample])

    threshold = float(np.percentile(null_spreads, percentile))
    return candidate_spread < threshold
