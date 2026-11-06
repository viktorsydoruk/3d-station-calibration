# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Least-squares camera calibration."""

__all__ = [
    "calibrate_camera",
]

import numpy as np
from scipy.optimize import OptimizeResult, least_squares

from ..models import SIGMA_OFFSET
from .initialization import estimate_r_initial, make_initial_parameters
from .model import residuals


def calibrate_camera(robot_positions: np.ndarray,
                     image_center_points: np.ndarray,
                     radii: np.ndarray,
                     sigmas: np.ndarray,
                     focal_length_initial: float = 2000.0,
                     camera_distance_initial: float = 80.0,
                     image_size_xy: tuple[int, int] = (2500, 2000),
                     fix_cx_cy: bool = False,
                     n_distortion_coefs: int = 5) -> OptimizeResult:
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
    :return: optimized results from least_squares of scipy module
    """

    sigmas = np.asarray(sigmas, dtype=np.float64) + SIGMA_OFFSET

    # estimate robot -> camera initial rotation
    r_initial = estimate_r_initial(robot_positions, image_center_points, radii, sigmas)

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

    initial_params = make_initial_parameters(
        focal_length=focal_length_initial,
        camera_distance=camera_distance_initial,
        image_size=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs,
        r_initial=r_initial,
    )

    result = least_squares(
        residuals,
        initial_params,
        args=(
            robot_positions,
            image_center_points
        ),
        kwargs={
            "n_distortion_coefs": n_distortion_coefs,
            "image_size": image_size_xy,
            "fix_cx_cy": fix_cx_cy,
        },

        loss="soft_l1",
        x_scale="jac",
    )

    return result
