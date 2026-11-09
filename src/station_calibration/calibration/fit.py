# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Least-squares camera calibration."""

__all__ = [
    "calibrate_camera",
]

import numpy as np
from scipy.optimize import OptimizeResult, least_squares

from ..models import (
    DEFAULT_LOSS_F_SCALE,
    SIGMA_OFFSET,
    validate_center_covariance,
)
from .initialization import estimate_r_initial, make_initial_parameters
from .model import residuals
from .weights import center_whitening_matrices, match_whitening_scale


def _validate_center_covariances(
    center_covariances: np.ndarray | None,
    n_points: int,
) -> np.ndarray | None:
    """Return a validated (N, 2, 2) covariance array or None."""
    if center_covariances is None:
        return None

    covariance = np.asarray(center_covariances, dtype=np.float64)
    if covariance.shape != (n_points, 2, 2):
        raise ValueError(
            "center_covariances must have shape "
            f"({n_points}, 2, 2), got {covariance.shape}"
        )

    validated = [validate_center_covariance(row) for row in covariance]
    return np.asarray(validated, dtype=np.float64)


def _run_least_squares(
    initial_params: np.ndarray,
    robot_positions: np.ndarray,
    image_center_points: np.ndarray,
    *,
    image_size_xy: tuple[int, int],
    fix_cx_cy: bool,
    n_distortion_coefs: int,
    loss_f_scale: float,
    whitening: np.ndarray | None,
) -> OptimizeResult:
    """Run one least-squares fit, optionally with whitened residuals."""
    return least_squares(
        residuals,
        initial_params,
        args=(robot_positions, image_center_points),
        kwargs={
            "n_distortion_coefs": n_distortion_coefs,
            "image_size": image_size_xy,
            "fix_cx_cy": fix_cx_cy,
            "whitening": whitening,
        },
        loss="soft_l1",
        f_scale=loss_f_scale,
        x_scale="jac",
    )


def calibrate_camera(robot_positions: np.ndarray,
                     image_center_points: np.ndarray,
                     radii: np.ndarray,
                     sigmas: np.ndarray,
                     focal_length_initial: float = 2000.0,
                     camera_distance_initial: float = 80.0,
                     image_size_xy: tuple[int, int] = (2500, 2000),
                     fix_cx_cy: bool = False,
                     n_distortion_coefs: int = 5,
                     loss_f_scale: float = DEFAULT_LOSS_F_SCALE,
                     center_covariances: np.ndarray | None = None) -> OptimizeResult:
    """
        Estimate camera intrinsics and extrinsics.

    :param robot_positions: positons of the center points (e.g., of a sphere hold by a robot) in space N*3
    :param image_center_points: positions of the center points on the images taken
    :param radii: radii of the sphere hold by a robot
    :param sigmas: bluring sigmas of the edges of the sphere hold by a robot
    :param focal_length_initial: initial focal length value
    :param camera_distance_initial: initial estimated distance of the focal plane to the camera
    :param image_size_xy: shape of the images taken
    :param fix_cx_cy: whether to fix the principal point (cx, cy) in the intrinsic matrix to be a half of image size
    :param n_distortion_coefs: number of distortion coefficients
    :param loss_f_scale: pixel scale at which the soft_l1 loss starts downweighting residuals
    :param center_covariances: optional (N, 2, 2) covariance of each measured image centre
    :return: optimized results from least_squares of scipy module
    """

    loss_f_scale = float(loss_f_scale)
    if not np.isfinite(loss_f_scale) or loss_f_scale <= 0:
        raise ValueError(
            f"loss_f_scale must be positive and finite, got {loss_f_scale}"
        )

    sigmas = np.asarray(sigmas, dtype=np.float64) + SIGMA_OFFSET

    robot_positions = np.asarray(robot_positions, dtype=np.float64)
    image_center_points = np.asarray(image_center_points, dtype=np.float64)

    if robot_positions.ndim != 2 or robot_positions.shape[1] != 3:
        raise ValueError(
            "robot_positions must have shape (N, 3)"
        )

    if image_center_points.ndim != 2 or image_center_points.shape[1] != 2:
        raise ValueError(
            "image_center_points must have shape (N, 2)"
        )

    if len(robot_positions) != len(image_center_points):
        raise ValueError(
            "robot_positions and image_center_points must have the same number of entries"
        )

    if len(robot_positions) < 10 + n_distortion_coefs:
        raise ValueError(
            f"At least {10 + n_distortion_coefs} measurements are recommended"
        )

    center_covariances = _validate_center_covariances(
        center_covariances,
        len(robot_positions),
    )

    # estimate robot -> camera initial rotation
    r_initial = estimate_r_initial(robot_positions, image_center_points, radii, sigmas)

    initial_params = make_initial_parameters(
        focal_length=focal_length_initial,
        camera_distance=camera_distance_initial,
        image_size=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs,
        r_initial=r_initial,
    )

    whitening = None
    if center_covariances is None:
        result = _run_least_squares(
            initial_params,
            robot_positions,
            image_center_points,
            image_size_xy=image_size_xy,
            fix_cx_cy=fix_cx_cy,
            n_distortion_coefs=n_distortion_coefs,
            loss_f_scale=loss_f_scale,
            whitening=None,
        )
    else:
        # The first fit supplies a robust raw-residual scale.  Only a global
        # scale of the whitening matrices is derived from it, so the parameter
        # estimate itself is not biased by the first pass.
        unweighted = _run_least_squares(
            initial_params,
            robot_positions,
            image_center_points,
            image_size_xy=image_size_xy,
            fix_cx_cy=fix_cx_cy,
            n_distortion_coefs=n_distortion_coefs,
            loss_f_scale=loss_f_scale,
            whitening=None,
        )
        raw_for_scale = residuals(
            unweighted.x,
            robot_positions,
            image_center_points,
            image_size=image_size_xy,
            fix_cx_cy=fix_cx_cy,
            n_distortion_coefs=n_distortion_coefs,
        )
        whitening = center_whitening_matrices(center_covariances)
        whitening = match_whitening_scale(whitening, raw_for_scale)
        result = _run_least_squares(
            unweighted.x,
            robot_positions,
            image_center_points,
            image_size_xy=image_size_xy,
            fix_cx_cy=fix_cx_cy,
            n_distortion_coefs=n_distortion_coefs,
            loss_f_scale=loss_f_scale,
            whitening=whitening,
        )

    # Keep the physically meaningful pixel residuals for RMSE reporting and
    # diagnostics; result.fun/result.jac remain the whitened quantities used by
    # the parameter covariance and the chi-square outlier test.
    raw_fun = residuals(
        result.x,
        robot_positions,
        image_center_points,
        image_size=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs,
    )
    setattr(result, "raw_fun", raw_fun)

    return result
