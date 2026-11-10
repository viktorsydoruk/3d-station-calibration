# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Functions related to robotic arm position calculations"""
import cv2
import numpy as np
from typing import Any

from .models import SIGMA_OFFSET

_N_SIGMA_GRID = np.linspace(0.0, 4.0, 100)
_N_SIGMA_BOOTSTRAP_LEVEL = 0.95


def find_robot_home_pos_shift(robot_positions: np.ndarray,
                              image_center_points: np.ndarray,
                              intrinsic_matrix: np.ndarray,
                              extrinsic_matrix: np.ndarray,
                              distortion: np.ndarray,
                              sigmas: np.ndarray) -> np.ndarray:
    """Estimation of the shift of the robotic arm home position based on sigma, cx and cy"""
    sigmas = np.asarray(sigmas, dtype=np.float64) + SIGMA_OFFSET

    # converting the robotic arm positions into the camera coordinate system
    coords = np.dot(extrinsic_matrix[None, :3, :3], robot_positions[:, :, None])[0, :, :, 0]
    # taking the distortion into account for the images center points
    image_center_points_undist = cv2.undistortImagePoints(image_center_points, intrinsic_matrix, distortion)[:, 0]

    # initialization
    d_home_pos = np.zeros(3, dtype=float)
    x_coords, y_coords, z_coords = coords
    x_im_coords, y_im_coords = image_center_points_undist.T
    r_from_c_xy = np.sqrt(x_coords**2 + y_coords**2)

    # z shift estimation using sigma of the blured edges
    popt = np.polyfit(z_coords, sigmas, deg=4, w=1/(r_from_c_xy**2+sigmas**2))
    x = np.linspace(np.min(z_coords), np.max(z_coords), 101)
    y = np.polyval(popt, x)
    d_home_pos[2] = x[np.argmin(y)]

    # x shift estimation using cx
    popt = np.polyfit(x_im_coords, x_coords, deg=1, w=1/sigmas**2)
    d_home_pos[0] = np.polyval(popt, intrinsic_matrix[0, 2])

    # y shift estimation using cy
    popt = np.polyfit(y_im_coords, y_coords, deg=1, w=1/sigmas**2)
    d_home_pos[1] = np.polyval(popt, intrinsic_matrix[1, 2])

    # converting back to the robotic coordinate system
    d_home_pos = np.dot(extrinsic_matrix[:3, :3].T, d_home_pos[:, None]).T[0]
    return d_home_pos


def _nozzle_radius_arrays(
    radii: np.ndarray,
    sigmas: np.ndarray,
    coef_for_radii: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return flat, same-length radius, sigma, and scale arrays."""
    radii = np.asarray(radii, dtype=np.float64).reshape(-1)
    sigmas = np.asarray(sigmas, dtype=np.float64).reshape(-1)
    coef_for_radii = np.asarray(coef_for_radii, dtype=np.float64).reshape(-1)
    if radii.size != sigmas.size or radii.size != coef_for_radii.size:
        raise ValueError(
            "radii, sigmas and coef_for_radii must have the same number of "
            f"values, got {radii.size}, {sigmas.size} and "
            f"{coef_for_radii.size}"
        )
    if radii.size == 0:
        raise ValueError("radii, sigmas and coef_for_radii must not be empty")
    return radii, sigmas, coef_for_radii


def _scan_n_sigma(
    radii: np.ndarray,
    sigmas: np.ndarray,
    coef_for_radii: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Scan the blur correction that minimises the diameter scatter."""
    diameters = 2.0 * radii * coef_for_radii
    sigma_terms = 2.0 * sigmas * coef_for_radii
    std_radii = np.asarray(
        [np.std(diameters - n_sigma * sigma_terms) for n_sigma in _N_SIGMA_GRID],
        dtype=np.float64,
    )
    n_sigma_opt = float(_N_SIGMA_GRID[int(np.argmin(std_radii))])
    return _N_SIGMA_GRID.copy(), std_radii, n_sigma_opt


def _ols_n_sigma(sigma_terms: np.ndarray, diameters: np.ndarray) -> float | None:
    """Least-squares slope of diameter against the sigma term."""
    centred = sigma_terms - sigma_terms.mean()
    denominator = float(np.dot(centred, centred))
    if denominator <= 0.0:
        return None
    slope = float(np.dot(centred, diameters - diameters.mean()) / denominator)
    return slope if np.isfinite(slope) else None


def _bootstrap_n_sigma_confidence(
    radii: np.ndarray,
    sigmas: np.ndarray,
    coef_for_radii: np.ndarray,
    *,
    n_bootstrap: int,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap a confidence interval for the blur correction.

    The scan is a grid approximation to the least-squares slope of the
    diameter on the sigma term.  Both the grid optimum and that continuous
    slope are bootstrapped so the reported interval is not limited to the
    scan step when the sample is large.
    """
    if n_bootstrap < 2:
        raise ValueError(
            f"n_sigma_bootstrap must be at least 2, got {n_bootstrap}"
        )

    diameters = 2.0 * radii * coef_for_radii
    sigma_terms = 2.0 * sigmas * coef_for_radii
    n_observations = diameters.size
    if n_observations < 3:
        return {
            "method": "bootstrap",
            "level": _N_SIGMA_BOOTSTRAP_LEVEL,
            "n_bootstrap": n_bootstrap,
            "n_valid": 0,
            "ci_low": None,
            "ci_high": None,
            "bootstrap_mean": None,
            "bootstrap_std": None,
            "continuous_opt": None,
            "continuous_ci_low": None,
            "continuous_ci_high": None,
            "continuous_bootstrap_std": None,
        }

    rng = np.random.default_rng(seed)
    grid_samples = np.empty(n_bootstrap, dtype=np.float64)
    continuous_samples = np.empty(n_bootstrap, dtype=np.float64)
    n_valid = 0
    for _ in range(n_bootstrap):
        indices = rng.integers(0, n_observations, n_observations)
        sampled_diameters = diameters[indices]
        sampled_sigma_terms = sigma_terms[indices]
        slope = _ols_n_sigma(sampled_sigma_terms, sampled_diameters)
        if slope is None:
            continue
        sampled_std = np.std(
            sampled_diameters[None, :]
            - _N_SIGMA_GRID[:, None] * sampled_sigma_terms[None, :],
            axis=1,
        )
        grid_samples[n_valid] = _N_SIGMA_GRID[int(np.argmin(sampled_std))]
        continuous_samples[n_valid] = slope
        n_valid += 1

    result: dict[str, Any] = {
        "method": "bootstrap",
        "level": _N_SIGMA_BOOTSTRAP_LEVEL,
        "n_bootstrap": n_bootstrap,
        "n_valid": n_valid,
        "ci_low": None,
        "ci_high": None,
        "bootstrap_mean": None,
        "bootstrap_std": None,
        "continuous_opt": _ols_n_sigma(sigma_terms, diameters),
        "continuous_ci_low": None,
        "continuous_ci_high": None,
        "continuous_bootstrap_std": None,
    }
    if n_valid < 2:
        return result

    grid_samples = grid_samples[:n_valid]
    continuous_samples = continuous_samples[:n_valid]
    percentiles = [
        0.5 * (1.0 - _N_SIGMA_BOOTSTRAP_LEVEL) * 100.0,
        0.5 * (1.0 + _N_SIGMA_BOOTSTRAP_LEVEL) * 100.0,
    ]
    grid_low, grid_high = np.percentile(grid_samples, percentiles)
    continuous_low, continuous_high = np.percentile(
        continuous_samples, percentiles
    )
    result.update(
        {
            "ci_low": float(grid_low),
            "ci_high": float(grid_high),
            "bootstrap_mean": float(np.mean(grid_samples)),
            "bootstrap_std": float(np.std(grid_samples, ddof=1)),
            "continuous_ci_low": float(continuous_low),
            "continuous_ci_high": float(continuous_high),
            "continuous_bootstrap_std": float(
                np.std(continuous_samples, ddof=1)
            ),
        }
    )
    return result


def get_nozzle_end_home_position(sphere_home_position: np.ndarray,
                                 robot_positions: np.ndarray,
                                 image_center_points: np.ndarray,
                                 intrinsic_matrix: np.ndarray,
                                 extrinsic_matrix: np.ndarray,
                                 distortion: np.ndarray,
                                 sigmas: np.ndarray,
                                 radii: np.ndarray,
                                 all_directions: np.ndarray,
                                 max_n_sigma: float | None = None,
                                 n_sigma_bootstrap: int = 0,
                                 n_sigma_bootstrap_seed: int = 0) -> tuple[np.ndarray, float, dict[str, dict[str, Any]]]:
    """Estimation of the shift of the robotic arm home position based on sigma, cx and cy"""
    debug_info = {}
    sigmas = np.asarray(sigmas, dtype=np.float64).reshape(-1) + SIGMA_OFFSET
    radii = np.asarray(radii, dtype=np.float64).reshape(-1)
    if n_sigma_bootstrap < 0:
        raise ValueError(
            "n_sigma_bootstrap must be non-negative, got "
            f"{n_sigma_bootstrap}"
        )
    if 0 < n_sigma_bootstrap < 2:
        raise ValueError(
            "n_sigma_bootstrap must be at least 2 when enabled, got "
            f"{n_sigma_bootstrap}"
        )

    directions = np.asarray(all_directions, dtype=np.float64).reshape(-1)
    if directions.size == 0:
        raise ValueError("all_directions must contain at least one nozzle direction")
    if not np.all(np.isfinite(directions)):
        raise ValueError("all_directions must contain only finite values")
    unique_directions = np.unique(directions)
    if unique_directions.size != 1 or unique_directions[0] not in (-1.0, 1.0):
        raise ValueError(
            "all_directions must contain a consistent +1 or -1 nozzle direction"
        )

    # converting the robotic arm positions into the camera coordinate system
    robot_camera_coords = np.dot(extrinsic_matrix[None, :3, :3], robot_positions[:, :, None])[0, :, :, 0]
    # taking the distortion into account for the images center points
    image_center_points_undist = cv2.undistortImagePoints(image_center_points, intrinsic_matrix, distortion)[:, 0]

    px = np.sqrt(np.sum((image_center_points_undist - intrinsic_matrix[:2, 2][None, :])**2, axis=1))
    mm = np.sqrt(np.sum(robot_camera_coords[:2]**2, axis=0))

    mask = mm > np.max(mm) / 2

    popt = np.polyfit(robot_camera_coords[2][mask], mm[mask]/px[mask], deg=2)
    debug_info['scaling_visualization'] = {
        'z_pos': robot_camera_coords[2][mask],
        'scale': mm[mask]/px[mask],
        'fit_popt': popt,
    }

    coef_for_radii = np.polyval(popt, robot_camera_coords[2])
    radii, sigmas, coef_for_radii = _nozzle_radius_arrays(
        radii, sigmas, coef_for_radii
    )

    n_sigmas, std_radii, n_sigma_opt = _scan_n_sigma(
        radii, sigmas, coef_for_radii
    )
    n_sigma_est = n_sigma_opt
    if max_n_sigma is not None:
        max_n_sigma = float(max_n_sigma)
        if not np.isfinite(max_n_sigma) or max_n_sigma < 0.0:
            raise ValueError(
                "max_n_sigma must be finite and non-negative, got "
                f"{max_n_sigma}"
            )
        n_sigma_est = min(n_sigma_est, max_n_sigma)

    confidence = None
    if n_sigma_bootstrap:
        confidence = _bootstrap_n_sigma_confidence(
            radii,
            sigmas,
            coef_for_radii,
            n_bootstrap=n_sigma_bootstrap,
            seed=n_sigma_bootstrap_seed,
        )

    debug_info['n_sigma_estimation'] = {
        'n_sigmas': n_sigmas,
        'std_radii': std_radii,
        'n_sigma_opt': n_sigma_opt,
        'max_n_sigma': max_n_sigma,
        'confidence': confidence,
    }

    sphere_radius = np.mean((radii-n_sigma_est*sigmas)*coef_for_radii)

    debug_info['sphere_radius_estimation'] = {
        'z_pos': robot_camera_coords[2],
        'radii': radii,
        'sigmas': sigmas,
        'coef_for_radii': coef_for_radii,
        'n_sigma_est' : n_sigma_est,
        'n_sigma_opt' : n_sigma_opt,
        'max_n_sigma' : max_n_sigma,

    }

    debug_info['sphere_radius_vs_depth'] = {
        'z_pos': robot_camera_coords[2],
        'radii': radii,
        'sigmas': sigmas,
        'coef_for_radii': np.polyval(popt, 0),
        'n_sigma_est' : n_sigma_est,

    }

    sign = float(unique_directions[0])
    # getting the nozzle end home position in camera coordinate system
    nozzle_end_home_position = (np.dot(extrinsic_matrix[:3, :3], sphere_home_position[:, None]).T[0]
                                + [0, sign*sphere_radius, 0])

    # converting the nozzle end home position to the robotic arm coordinate system
    nozzle_end_home_position = np.dot(extrinsic_matrix[:3, :3].T, nozzle_end_home_position[:, None]).T[0]
    if (
        not np.all(np.isfinite(nozzle_end_home_position))
        or not np.isfinite(sphere_radius)
        or sphere_radius <= 0.0
    ):
        raise ValueError(
            "estimated nozzle position and sphere radius must be finite and positive"
        )
    return nozzle_end_home_position, sphere_radius*2, debug_info
