# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Calibration diagnostics, uncertainty propagation, and reporting."""

__all__ = [
    "check_distortion_monotonicity",
    "calculate_calibration_errors",
    "print_calibration",
    "back_projected_point",
    "calculate_RMSE",
]

import cv2
import numpy as np
from scipy.optimize import OptimizeResult

from ..support import calculate_errors
from .model import get_calibration, params_names


def check_distortion_monotonicity(distortion: np.ndarray,
                                  intrinsic_matrix: np.ndarray,
                                  image_size_xy: tuple = (2500, 2000),
                                  ) -> bool:
    """
        Checking the monotonic behaviour of distortion function 1 + k1*r**2 + k2*r**4 + k3*r**6
    :param distortion: distortion vector
    :param intrinsic_matrix: intrinsic matrix
    :param image_size_xy: image size (x, y)
    :return: boolean value
    """
    # defining the max related radius and related radius values
    r_max = np.sqrt((image_size_xy[0] / 2) ** 2 + (image_size_xy[1] / 2) ** 2) / intrinsic_matrix[0, 0]
    r_val = np.linspace(0, r_max, 101)

    # calculating
    func_val = 1 + distortion[0] * r_val ** 2 + distortion[1] * r_val ** 4 + distortion[4] * r_val ** 6
    dfunc_val = np.diff(func_val)
    return np.all(dfunc_val >= 0) or np.all(dfunc_val <= 0)


def calculate_calibration_errors(result: OptimizeResult,
                                 fix_cx_cy: bool = False,
                                 n_distortion_coefs: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    intrinsic_std, distortion_std, rot_vec_std, extrinsic_std = get_calibration(
        calculate_errors(result),
        image_size_xy=(0, 0),
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )
    return intrinsic_std, distortion_std, rot_vec_std, extrinsic_std[:3, 3]


def print_calibration(result: OptimizeResult,
                      image_size_xy: tuple = (2500, 2000),
                      fix_cx_cy: bool = False,
                      n_distortion_coefs: int = 5) -> None:

    intrinsic_matrix, distortion, rvec, extrinsic_matrix = get_calibration(
        result.x,
        image_size_xy=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )

    print()
    print("-" * 60)
    print("CALIBRATION RESULT")
    print("-" * 60)

    print()
    print("Intrinsic matrix:")

    print(intrinsic_matrix)

    print()
    print("Distortion coefficients:")
    print(distortion)

    print()
    print("Rotation vector:")
    print(rvec)

    print()
    print("Extrinsic matrix:")
    print(extrinsic_matrix)

    print()
    print("Optimization:")
    print("success:", result.success)
    print("message:", result.message)
    print("cost:", result.cost)
    print("fit values:")
    names = params_names(
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )
    for each_err, each_value, each_name in zip(calculate_errors(result), result.x, names):
        print(f"{each_name:>6}: {each_value:>15.5f} +/- {each_err:0.5f}")


def back_projected_point(robot_pos: np.ndarray,
                         intrinsic_matrix: np.ndarray,
                         extrinsic_matrix: np.ndarray,
                         distortion: np.ndarray) -> np.ndarray:
    """
        Back projecting 3D point to 2D image
    :param robot_pos: 3D points to project
    :param intrinsic_matrix: intrinsic matrix
    :param extrinsic_matrix: extrinsic matrix
    :param distortion:
    :return:
    """
    R = extrinsic_matrix[:3, :3]
    tvec = extrinsic_matrix[:3, 3]
    rvec = cv2.Rodrigues(R)[0].reshape(-1)
    return cv2.projectPoints(
        robot_pos,
        rvec,
        tvec,
        intrinsic_matrix,
        distortion
    )[0][:, 0]


def calculate_RMSE(result: OptimizeResult,
                   standardized: bool = True) -> float:
    res = result.fun
    mse = np.mean(res**2)
    rmse = np.sqrt(mse)
    if standardized:
        rmse /= len(res)

    return rmse
