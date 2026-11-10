# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Residual-bootstrap uncertainty for the nozzle home position.

The camera fit reports uncertainties for the intrinsic/extrinsic parameters,
but the nozzle home position is computed after the fit from the sphere-home
position, the sphere radius, and the image/robot geometry.  Those quantities are
not part of ``OptimizeResult.jac``, so their uncertainty cannot be obtained from
:func:`calculate_calibration_errors` alone.

This module implements a residual bootstrap around the existing estimator:

* image centres are perturbed using their measured 2x2 covariance;
* radius and blur-sigma residuals are resampled from the smooth trends used by
  the nozzle estimator;
* the commanded robot positions are kept fixed;
* the camera fit and the nozzle estimator are rerun for every replicate.

The reported covariance is conditional on the original inlier selection.  The
bootstrap does not model robot-positioning errors or a wrong sphere diameter;
both are deliberate choices matching the data-acquisition assumptions.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .debug import DebugInfo
from .models import (
    SIGMA_OFFSET,
    CalibrationObservation,
    CalibrationResult,
)
from .processes import get_calibration_data
from .robot import get_nozzle_end_home_position
from .settings import Settings
from .support import reported, reported_error

__all__ = [
    "NozzleBootstrapResult",
    "bootstrap_nozzle_home",
]


@dataclass(frozen=True)
class NozzleBootstrapResult:
    """Result of a nozzle-home residual bootstrap.

    All positions, standard deviations, and confidence bounds are in
    millimetres and in the robot coordinate system.
    """

    original: np.ndarray
    samples: np.ndarray
    mean: np.ndarray
    bias: np.ndarray
    covariance: np.ndarray
    std: np.ndarray
    norm_std: float
    axis: np.ndarray
    along_std: float
    perpendicular_std: float
    lower_1sigma: np.ndarray
    upper_1sigma: np.ndarray
    lower_2sigma: np.ndarray
    upper_2sigma: np.ndarray
    n_requested: int
    n_success: int
    n_failed: int
    failure_messages: tuple[str, ...]
    mode: str = "residual"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary.

        The summary vectors are rounded to two significant digits of their
        bootstrap one-sigma. ``samples`` and ``covariance`` keep full precision
        because they describe the replicate distribution rather than a single
        reported measurement.
        """
        std = np.asarray(self.std, dtype=np.float64)
        return {
            "mode": self.mode,
            "n_requested": self.n_requested,
            "n_success": self.n_success,
            "n_failed": self.n_failed,
            "failure_messages": list(self.failure_messages),
            "samples": self.samples.tolist(),
            "original": _reported_vector(self.original, std),
            "mean": _reported_vector(self.mean, std),
            "bias": _reported_vector(self.bias, std),
            "std": [reported_error(value) for value in std],
            "norm_std": reported_error(self.norm_std),
            "covariance": self.covariance.tolist(),
            "axis": self.axis.tolist(),
            "along_std": reported_error(self.along_std),
            "perpendicular_std": reported_error(self.perpendicular_std),
            "lower_1sigma": _reported_vector(self.lower_1sigma, std),
            "upper_1sigma": _reported_vector(self.upper_1sigma, std),
            "lower_2sigma": _reported_vector(self.lower_2sigma, std),
            "upper_2sigma": _reported_vector(self.upper_2sigma, std),
        }


def _reported_vector(values: np.ndarray, std: np.ndarray) -> list[float]:
    """Round a vector to the decimal places of its per-component one-sigma."""
    array = np.asarray(values, dtype=np.float64)
    errors = np.broadcast_to(np.asarray(std, dtype=np.float64), array.shape)
    return [
        reported(value, error)[0]
        for value, error in zip(array.ravel(), errors.ravel())
    ]


def _ensure_symmetric_psd(covariance: np.ndarray) -> np.ndarray:
    """Symmetrize a 2x2 covariance and clip round-off negative eigenvalues."""
    matrix = np.asarray(covariance, dtype=np.float64)
    if matrix.shape != (2, 2) or not np.all(np.isfinite(matrix)):
        raise ValueError("center covariance must be a finite 2x2 matrix")
    matrix = 0.5 * (matrix + matrix.T)
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    if float(eigenvalues[0]) < -1e-8 * max(1.0, float(eigenvalues[-1])):
        raise ValueError(f"center covariance is not positive semidefinite: {eigenvalues}")
    return eigenvectors @ np.diag(np.maximum(eigenvalues, 0.0)) @ eigenvectors.T


def _estimate_global_center_covariance(result: CalibrationResult) -> np.ndarray:
    """Estimate a fallback centre covariance from the fit residuals."""
    raw = getattr(result.optimize_result, "raw_fun", None)
    if raw is not None:
        residuals = np.asarray(raw, dtype=np.float64)
        if residuals.ndim == 1 and residuals.size and residuals.size % 2 == 0:
            residuals = residuals.reshape(-1, 2)
        if (
            residuals.ndim == 2
            and residuals.shape[1] == 2
            and residuals.shape[0] >= 2
            and np.all(np.isfinite(residuals))
        ):
            covariance = np.cov(residuals, rowvar=False)
            if covariance.shape == (2, 2) and np.all(np.isfinite(covariance)):
                return _ensure_symmetric_psd(covariance)

    sigma = float(result.rmse)
    if not np.isfinite(sigma) or sigma <= 0.0:
        sigma = 1.0
    return np.eye(2, dtype=np.float64) * sigma**2


def _sample_center_offset(covariance: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Draw one zero-mean 2D offset from a covariance matrix."""
    eigenvalues, eigenvectors = np.linalg.eigh(_ensure_symmetric_psd(covariance))
    return eigenvectors @ (np.sqrt(np.maximum(eigenvalues, 0.0)) * rng.standard_normal(2))


def _inlier_arrays(
    fit_observations: Sequence[CalibrationObservation],
    result: CalibrationResult,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray | None,
]:
    """Return inlier arrays, adjusted centres, and per-point centre covariances."""
    observations = list(fit_observations)
    mask = np.asarray(result.fit_mask, dtype=bool)
    if mask.shape != (len(observations),):
        raise ValueError(
            "result.fit_mask must have one entry per fit observation, "
            f"got {mask.shape} for {len(observations)} observations"
        )

    inliers = [observations[i] for i in np.flatnonzero(mask)]
    if not inliers:
        raise ValueError("the fit has no inlier observations to bootstrap")

    robot_positions = np.asarray([obs.robot_position for obs in inliers], dtype=np.float64)
    center_points = np.asarray([obs.image_center for obs in inliers], dtype=np.float64)
    radii = np.asarray([obs.radius for obs in inliers], dtype=np.float64)
    sigmas = np.asarray([obs.sigma for obs in inliers], dtype=np.float64)
    directions = np.asarray([obs.direction for obs in inliers], dtype=np.float64)
    center_points_adjusted = np.asarray(result.center_points_adjusted, dtype=np.float64)[mask]

    covariances = [obs.center_covariance for obs in inliers]
    validated_covariances: list[np.ndarray] = []
    for covariance in covariances:
        if covariance is None:
            center_covariances = None
            break
        validated_covariances.append(_ensure_symmetric_psd(covariance))
    else:
        center_covariances = np.stack(validated_covariances)

    return (
        robot_positions,
        center_points,
        radii,
        sigmas,
        directions,
        center_points_adjusted,
        center_covariances,
    )


def _radius_sigma_predictions(
    robot_positions: np.ndarray,
    radii: np.ndarray,
    sigmas: np.ndarray,
    result: CalibrationResult,
    sphere_diameter: float,
    debug_info: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return smooth radius/sigma predictions and their residuals.

    The trends mirror the estimators in :mod:`station_calibration.robot`: a
    quartic sigma-versus-depth fit and the radius scaling polynomial.  Resampling
    the residuals preserves the observed depth-dependent scatter instead of
    assuming a constant noise level.
    """
    rotation = np.asarray(result.extrinsic_matrix[:3, :3], dtype=np.float64)
    relative_positions = np.asarray(robot_positions, dtype=np.float64) - np.asarray(
        result.pos_home, dtype=np.float64
    )
    camera_positions = relative_positions @ rotation.T
    z_positions = camera_positions[:, 2]
    radial_distance = np.hypot(camera_positions[:, 0], camera_positions[:, 1])

    adjusted_sigmas = np.asarray(sigmas, dtype=np.float64) + SIGMA_OFFSET
    weights = 1.0 / (radial_distance**2 + adjusted_sigmas**2)
    try:
        sigma_coefficients = np.polyfit(
            z_positions,
            adjusted_sigmas,
            deg=4,
            w=weights,
        )
    except (np.linalg.LinAlgError, ValueError):
        sigma_coefficients = np.polyfit(
            z_positions,
            adjusted_sigmas,
            deg=1,
            w=weights,
        )
    predicted_sigmas = np.polyval(sigma_coefficients, z_positions)

    estimation = debug_info.get("sphere_radius_estimation", {})
    coefficients = np.asarray(estimation.get("coef_for_radii"), dtype=np.float64)
    n_sigma_est = float(estimation.get("n_sigma_est", 0.0))
    if (
        coefficients.shape != radii.shape
        or not np.all(np.isfinite(coefficients))
        or np.any(coefficients == 0.0)
    ):
        raise ValueError("the nozzle estimator did not provide usable radius scaling coefficients")

    sphere_radius = 0.5 * float(sphere_diameter)
    predicted_radii = sphere_radius / coefficients + n_sigma_est * adjusted_sigmas

    radius_residuals = radii - predicted_radii
    sigma_residuals = adjusted_sigmas - predicted_sigmas
    # Residual bootstrap distributions must be centred on the fitted trend;
    # otherwise a non-zero weighted-fit residual mean shifts every replicate.
    radius_residuals = radius_residuals - radius_residuals.mean()
    sigma_residuals = sigma_residuals - sigma_residuals.mean()

    return (
        predicted_radii,
        radius_residuals,
        predicted_sigmas,
        sigma_residuals,
    )


def _nozzle_for_result(
    robot_positions: np.ndarray,
    center_points_adjusted: np.ndarray,
    radii: np.ndarray,
    sigmas: np.ndarray,
    directions: np.ndarray,
    pos_home: np.ndarray,
    intrinsic_matrix: np.ndarray,
    extrinsic_matrix: np.ndarray,
    distortion: np.ndarray,
    max_n_sigma: float | None = None,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    """Call the production nozzle estimator for one fit result."""
    relative_positions = np.asarray(robot_positions) - np.asarray(pos_home)
    return get_nozzle_end_home_position(
        sphere_home_position=np.asarray(pos_home, dtype=np.float64),
        robot_positions=relative_positions,
        image_center_points=np.asarray(center_points_adjusted, dtype=np.float64),
        intrinsic_matrix=np.asarray(intrinsic_matrix, dtype=np.float64),
        extrinsic_matrix=np.asarray(extrinsic_matrix, dtype=np.float64),
        distortion=np.asarray(distortion, dtype=np.float64),
        sigmas=np.asarray(sigmas, dtype=np.float64),
        radii=np.asarray(radii, dtype=np.float64),
        all_directions=np.asarray(directions, dtype=np.float64),
        max_n_sigma=max_n_sigma,
    )


def _nozzle_axis(direction: float, result: CalibrationResult) -> np.ndarray:
    """Return the unit nozzle-offset direction in robot coordinates."""
    rotation = np.asarray(result.extrinsic_matrix[:3, :3], dtype=np.float64)
    axis = float(direction) * (rotation.T @ np.array([0.0, 1.0, 0.0], dtype=np.float64))
    norm = float(np.linalg.norm(axis))
    if not np.isfinite(norm) or norm <= 0.0:
        return np.array([0.0, 1.0, 0.0], dtype=np.float64)
    return axis / norm


def _statistics(
    samples: np.ndarray,
    original: np.ndarray,
    axis: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    float,
    float,
    float,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Compute mean, covariance, standard deviations, and intervals."""
    mean = samples.mean(axis=0)
    if samples.shape[0] >= 2:
        covariance = np.cov(samples, rowvar=False, ddof=1)
    else:
        covariance = np.zeros((3, 3), dtype=np.float64)
    covariance = 0.5 * (covariance + covariance.T)
    std = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    norm_std = float(np.sqrt(max(float(np.trace(covariance)), 0.0)))

    unit_axis = np.asarray(axis, dtype=np.float64)
    norm = float(np.linalg.norm(unit_axis))
    if not np.isfinite(norm) or norm <= 0.0:
        unit_axis = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    else:
        unit_axis = unit_axis / norm
    along_variance = float(unit_axis @ covariance @ unit_axis)
    perpendicular_variance = max(float(np.trace(covariance)) - along_variance, 0.0)

    lower_1sigma, upper_1sigma = np.percentile(samples, [15.865, 84.135], axis=0)
    lower_2sigma, upper_2sigma = np.percentile(samples, [2.5, 97.5], axis=0)
    bias = mean - original

    return (
        mean,
        bias,
        covariance,
        std,
        norm_std,
        float(np.sqrt(along_variance)),
        float(np.sqrt(perpendicular_variance)),
        lower_1sigma,
        upper_1sigma,
        lower_2sigma,
        upper_2sigma,
    )


def bootstrap_nozzle_home(
    fit_observations: Sequence[CalibrationObservation],
    result: CalibrationResult,
    settings: Settings,
    *,
    n_bootstrap: int = 500,
    seed: int | None = 0,
) -> NozzleBootstrapResult:
    """Estimate the nozzle-home uncertainty by residual bootstrap.

    Parameters
    ----------
    fit_observations:
        Observations passed to the fit, in the order used by ``result``.
    result:
        Calibration result whose inliers are bootstrapped.
    settings:
        Settings used for the original fit.  A shallow copy with
        ``allowed_outliers = 0`` is used for the replicates so the original
        inlier selection is held fixed.
    n_bootstrap:
        Number of bootstrap replicates.
    seed:
        Seed for the random generator.  Use ``None`` for a fresh stream.

    Returns
    -------
    NozzleBootstrapResult
        Samples, covariance, standard deviations, and confidence intervals.
    """
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap must be at least 1, got {n_bootstrap}")

    observations = list(fit_observations)
    (
        robot_positions,
        center_points,
        radii,
        sigmas,
        directions,
        center_points_adjusted,
        center_covariances,
    ) = _inlier_arrays(observations, result)

    global_center_covariance = _estimate_global_center_covariance(result)
    if center_covariances is None:
        perturbation_covariances = np.repeat(
            global_center_covariance[None, :, :],
            len(radii),
            axis=0,
        )
    else:
        perturbation_covariances = center_covariances

    max_n_sigma = (
        settings.subpixel_max_n_sigma if settings.subpixel_edges else None
    )
    original_nozzle, sphere_diameter, debug_info = _nozzle_for_result(
        robot_positions=robot_positions,
        center_points_adjusted=center_points_adjusted,
        radii=radii,
        sigmas=sigmas,
        directions=directions,
        pos_home=result.pos_home,
        intrinsic_matrix=result.intrinsic_matrix,
        extrinsic_matrix=result.extrinsic_matrix,
        distortion=result.distortion,
        max_n_sigma=max_n_sigma,
    )

    (
        predicted_radii,
        radius_residuals,
        predicted_sigmas,
        sigma_residuals,
    ) = _radius_sigma_predictions(
        robot_positions,
        radii,
        sigmas,
        result,
        sphere_diameter,
        debug_info,
    )

    rng = np.random.default_rng(seed)
    settings_without_outlier_removal = copy(settings)
    settings_without_outlier_removal.allowed_outliers = 0

    samples: list[np.ndarray] = []
    failure_messages: list[str] = []
    for _ in range(n_bootstrap):
        try:
            center_offsets = np.asarray(
                [
                    _sample_center_offset(covariance, rng)
                    for covariance in perturbation_covariances
                ],
                dtype=np.float64,
            )
            perturbed_centers = center_points + center_offsets

            residual_indices = rng.integers(0, len(radii), len(radii))
            perturbed_radii = np.maximum(
                predicted_radii + radius_residuals[residual_indices],
                np.finfo(np.float64).eps,
            )
            perturbed_sigmas = np.maximum(
                predicted_sigmas - SIGMA_OFFSET + sigma_residuals[residual_indices],
                0.0,
            )

            (
                pos_home,
                adjusted_centers,
                intrinsic_matrix,
                extrinsic_matrix,
                distortion,
                _,
                _,
                _,
                _,
            ) = get_calibration_data(
                robot_positions,
                perturbed_centers,
                perturbed_radii,
                perturbed_sigmas,
                result.image_size_xy,
                settings_without_outlier_removal,
                DebugInfo(False),
                center_covariances=center_covariances,
            )

            nozzle, _, _ = _nozzle_for_result(
                robot_positions=robot_positions,
                center_points_adjusted=adjusted_centers,
                radii=perturbed_radii,
                sigmas=perturbed_sigmas,
                directions=directions,
                pos_home=pos_home,
                intrinsic_matrix=intrinsic_matrix,
                extrinsic_matrix=extrinsic_matrix,
                distortion=distortion,
                max_n_sigma=max_n_sigma,
            )
        except Exception as error:
            failure_messages.append(f"{type(error).__name__}: {error}")
            continue

        samples.append(np.asarray(nozzle, dtype=np.float64))

    if not samples:
        raise RuntimeError(
            "all nozzle bootstrap replicates failed; first failure: "
            + (failure_messages[0] if failure_messages else "unknown")
        )

    sample_array = np.asarray(samples, dtype=np.float64)
    axis = _nozzle_axis(float(directions[0]), result)
    (
        mean,
        bias,
        covariance,
        std,
        norm_std,
        along_std,
        perpendicular_std,
        lower_1sigma,
        upper_1sigma,
        lower_2sigma,
        upper_2sigma,
    ) = _statistics(sample_array, original_nozzle, axis)

    return NozzleBootstrapResult(
        original=np.asarray(original_nozzle, dtype=np.float64),
        samples=sample_array,
        mean=mean,
        bias=bias,
        covariance=covariance,
        std=std,
        norm_std=norm_std,
        axis=axis,
        along_std=along_std,
        perpendicular_std=perpendicular_std,
        lower_1sigma=lower_1sigma,
        upper_1sigma=upper_1sigma,
        lower_2sigma=lower_2sigma,
        upper_2sigma=upper_2sigma,
        n_requested=n_bootstrap,
        n_success=len(samples),
        n_failed=len(failure_messages),
        failure_messages=tuple(failure_messages[:5]),
    )
