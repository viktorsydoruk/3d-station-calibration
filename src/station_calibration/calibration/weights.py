# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Whitening transforms for per-observation centre covariances."""

__all__ = [
    "center_whitening_matrices",
    "match_whitening_scale",
    "whiten_residuals",
]

import numpy as np


def _robust_scale(values: np.ndarray) -> float:
    """Return a robust Gaussian-equivalent scale for arbitrary residuals."""
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = flat[np.isfinite(flat)]
    if finite.size == 0:
        return float("nan")

    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    if np.isfinite(mad) and mad > 0.0:
        return 1.4826 * mad

    rms = float(np.sqrt(np.mean(finite ** 2)))
    return rms if np.isfinite(rms) else float("nan")


def center_whitening_matrices(
    center_covariances: np.ndarray,
    *,
    relative_floor: float = 1e-6,
) -> np.ndarray:
    """Return lower-triangular whitening matrices for centre covariances.

    A residual ``r_i`` with covariance ``C_i`` is whitened as
    ``L_i^-1 r_i``, where ``L_i L_i^T = C_i``.  The result has an identity
    covariance when the supplied covariance model is correct.

    Very small or singular covariances are regularised relative to the median
    covariance scale. This keeps near-degenerate circle fits from dominating
    the fit with an arbitrarily large weight.
    """
    covariance = np.asarray(center_covariances, dtype=np.float64)
    if covariance.ndim != 3 or covariance.shape[1:] != (2, 2):
        raise ValueError(
            "center_covariances must have shape (N, 2, 2), "
            f"got {covariance.shape}"
        )
    if not np.all(np.isfinite(covariance)):
        raise ValueError("center_covariances must contain only finite values")

    covariance = 0.5 * (covariance + np.swapaxes(covariance, -1, -2))
    if not relative_floor > 0.0:
        raise ValueError(
            f"relative_floor must be positive, got {relative_floor}"
        )

    diagonal_scale = float(np.median(np.trace(covariance, axis1=1, axis2=2)))
    if not np.isfinite(diagonal_scale) or diagonal_scale <= 0.0:
        diagonal_scale = 1.0
    floor = float(relative_floor) * diagonal_scale

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, floor)
    regularised = (
        eigenvectors
        @ (eigenvalues[..., :, None] * np.swapaxes(eigenvectors, -1, -2))
    )
    regularised = 0.5 * (regularised + np.swapaxes(regularised, -1, -2))

    cholesky = np.linalg.cholesky(regularised)
    return np.linalg.inv(cholesky)


def whiten_residuals(
    residuals: np.ndarray,
    whitening: np.ndarray,
) -> np.ndarray:
    """Apply per-observation whitening matrices to 2D residuals."""
    error = np.asarray(residuals, dtype=np.float64)
    transform = np.asarray(whitening, dtype=np.float64)
    if error.shape != transform.shape[:1] + (2,):  # pragma: no cover - defensive
        raise ValueError(
            "residuals must have shape (N, 2) matching the whitening matrices"
        )
    return np.einsum("nij,nj->ni", transform, error)


def match_whitening_scale(
    whitening: np.ndarray,
    raw_residuals: np.ndarray,
) -> np.ndarray:
    """Rescale whitening so whitened residuals keep the raw pixel scale.

    The parameter estimates are invariant to a global scaling of the weights,
    but the robust loss threshold ``loss_f_scale`` is expressed in pixels.  A
    global factor makes the whitened residual scale comparable to the raw
    reprojection scale, so the configured threshold keeps its intended meaning.
    """
    raw = np.asarray(raw_residuals, dtype=np.float64).reshape(-1)
    white = whiten_residuals(
        np.asarray(raw_residuals, dtype=np.float64).reshape(-1, 2),
        whitening,
    ).reshape(-1)
    raw_scale = _robust_scale(raw)
    white_scale = _robust_scale(white)
    if (
        not np.isfinite(raw_scale)
        or not np.isfinite(white_scale)
        or raw_scale <= 0.0
        or white_scale <= 0.0
    ):
        return np.asarray(whitening, dtype=np.float64)
    return np.asarray(whitening, dtype=np.float64) * (raw_scale / white_scale)
