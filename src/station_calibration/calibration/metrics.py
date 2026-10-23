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


def _radial_distortion_coefficients(distortion: np.ndarray) -> np.ndarray:
    """Return k1, k2, k3, k4, k5, k6 from an OpenCV distortion vector."""
    coefficients = np.asarray(distortion, dtype=np.float64).reshape(-1)
    if coefficients.size < 8:
        coefficients = np.pad(coefficients, (0, 8 - coefficients.size))
    return coefficients[[0, 1, 4, 5, 6, 7]]


def check_distortion_monotonicity(distortion: np.ndarray,
                                  intrinsic_matrix: np.ndarray,
                                  image_size_xy: tuple = (2500, 2000),
                                  ) -> bool:
    """Check that the radial distortion scale is positive and monotonic.

    OpenCV stores the radial coefficients as ``k1, k2, k3, k4, k5, k6`` at
    indices 0, 1, 4, 5, 6, and 7. The radial scale is

    ``1 + k1*r**2 + k2*r**4 + ... + k6*r**12``.

    It must remain positive and have a consistent derivative sign over the
    image domain. Tangential and tilt terms do not enter the radial scale.

    :param distortion: OpenCV distortion vector
    :param intrinsic_matrix: intrinsic matrix
    :param image_size_xy: image size (x, y)
    :return: ``True`` when the radial model is usable over the image
    """
    distortion = np.asarray(distortion, dtype=np.float64).reshape(-1)
    intrinsic_matrix = np.asarray(intrinsic_matrix, dtype=np.float64)

    if distortion.size == 0:
        return True
    if not np.all(np.isfinite(distortion)):
        return False
    if intrinsic_matrix.shape != (3, 3) or not np.all(np.isfinite(intrinsic_matrix)):
        return False

    focal_length = abs(float(intrinsic_matrix[0, 0]))
    width, height = image_size_xy
    if focal_length == 0.0 or width <= 0 or height <= 0:
        return False

    r_max = float(np.hypot(width / 2.0, height / 2.0) / focal_length)
    if not np.isfinite(r_max) or r_max <= 0.0:
        return False

    k1, k2, k3, k4, k5, k6 = _radial_distortion_coefficients(distortion)
    r_val = np.linspace(0.0, r_max, 1001)
    r2 = r_val ** 2

    scale = (
        1.0
        + k1 * r2
        + k2 * r2 ** 2
        + k3 * r2 ** 3
        + k4 * r2 ** 4
        + k5 * r2 ** 5
        + k6 * r2 ** 6
    )
    if not np.all(np.isfinite(scale)) or np.any(scale <= 0.0):
        return False

    derivative = (
        2.0 * k1 * r_val
        + 4.0 * k2 * r_val ** 3
        + 6.0 * k3 * r_val ** 5
        + 8.0 * k4 * r_val ** 7
        + 10.0 * k5 * r_val ** 9
        + 12.0 * k6 * r_val ** 11
    )
    tolerance = max(1e-12, 1e-10 * float(np.max(np.abs(derivative))))
    return bool(
        np.all(derivative >= -tolerance)
        or np.all(derivative <= tolerance)
    )


def calculate_calibration_errors(result: OptimizeResult,
                                 fix_cx_cy: bool = False,
                                 n_distortion_coefs: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    errors = np.asarray(calculate_errors(result), dtype=np.float64).reshape(-1)

    intrinsic_std = np.zeros((3, 3), dtype=np.float64)
    intrinsic_std[2, 2] = 1.0
    intrinsic_std[0, 0] = errors[0]
    intrinsic_std[1, 1] = errors[1]

    offset = 2
    if not fix_cx_cy:
        intrinsic_std[0, 2] = errors[2]
        intrinsic_std[1, 2] = errors[3]
        offset = 4

    n_distortion_coefs = int(n_distortion_coefs)
    distortion_std = np.zeros(14, dtype=np.float64)
    distortion_std[:n_distortion_coefs] = errors[offset:offset + n_distortion_coefs]
    offset += n_distortion_coefs

    rot_vec_std = errors[offset:offset + 3].copy()
    offset += 3
    tra_vec_std = errors[offset:offset + 3].copy()

    return intrinsic_std, distortion_std, rot_vec_std, tra_vec_std


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
    """Return the root-mean-square reprojection error.

    With ``standardized=False`` the usual RMSE over all residual components is
    returned. With ``standardized=True`` the sum of squared residuals is divided
    by the residual degrees of freedom (``m - n``), giving the residual standard
    error. The standardized value is ``nan`` when no degrees of freedom remain.
    """
    residuals = np.asarray(result.fun, dtype=np.float64).reshape(-1)
    if residuals.size == 0:
        return float("nan")
    if not np.all(np.isfinite(residuals)):
        return float("nan")

    sum_squares = float(np.dot(residuals, residuals))
    if not standardized:
        return float(np.sqrt(sum_squares / residuals.size))

    jacobian = np.asarray(result.jac, dtype=np.float64)
    if jacobian.ndim != 2 or jacobian.shape[0] != residuals.size:
        raise ValueError(
            "result.jac must be a 2D array with one row per residual"
        )

    degrees_of_freedom = residuals.size - jacobian.shape[1]
    if degrees_of_freedom <= 0:
        return float("nan")
    return float(np.sqrt(sum_squares / degrees_of_freedom))
