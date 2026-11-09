# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Camera-model parameter packing, projection, and unwrapping."""

__all__ = [
    "unwrap_params",
    "unwrap_k_distortion_params",
    "params_names",
    "project_points",
    "residuals",
    "get_calibration",
]

import cv2
import numpy as np


def unwrap_params(params: np.ndarray,
                  image_size: tuple = (2500, 2000),
                  fix_cx_cy: bool = False,
                  n_distortion_coefs: int = 5) -> tuple[float , float, float, float, np.ndarray, np.ndarray, np.ndarray]:
    """Unwrapping the parameters for least-square problem"""
    _end_arg = 0
    fx, fy = params[_end_arg:_end_arg + 2]
    _end_arg += 2

    if not fix_cx_cy:
        cx, cy = params[_end_arg:_end_arg + 2]
        _end_arg += 2
    else:
        cx = image_size[0] / 2
        cy = image_size[1] / 2

    distortion = np.zeros(14, dtype=np.float64)
    distortion[:n_distortion_coefs] = params[_end_arg:_end_arg + n_distortion_coefs]
    _end_arg += n_distortion_coefs

    rvec = params[_end_arg:_end_arg + 3]
    _end_arg += 3

    tvec = params[_end_arg:_end_arg + 3]
    _end_arg += 3

    return fx, fy, cx, cy, distortion, rvec, tvec


def unwrap_k_distortion_params(params: np.ndarray,
                               fix_cx_cy: bool = False,
                               n_distortion_coefs: int = 5) -> np.ndarray:
    """Unwrapping the distortion parameters"""
    _end_arg = 2

    if not fix_cx_cy:
        _end_arg += 2

    distortion = np.zeros(14, dtype=np.float64)
    distortion[:n_distortion_coefs] = params[_end_arg:_end_arg + n_distortion_coefs]

    return distortion


def params_names(fix_cx_cy: bool = False,
                 n_distortion_coefs: int = 5) -> list[str]:
    """Unwrapping the parameters for least-square problem"""
    all_names = ["fx", "fy"]

    if not fix_cx_cy:
        all_names += ["cx", "cy"]

    all_names += ["k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6", "s1", "s2", "s3", "s4", "τx", "τy"][:n_distortion_coefs]
    all_names += ["r1", "r2", "r3", "t1", "t2", "t3"]

    return all_names


def project_points(params: np.ndarray,
                   robot_points: np.ndarray,
                   image_size: tuple = (2500, 2000),
                   fix_cx_cy: bool = False,
                   n_distortion_coefs: int = 5) -> np.ndarray:
    """
        Transform robot coordinates to camera coordinates and project them into the image.
    :param params:
    :param robot_points:
    :param image_size:
    :param fix_cx_cy:
    :param n_distortion_coefs:
    :return:
    """
    fx, fy, cx, cy, distortion, rvec, tvec = unwrap_params(
        params,
        image_size,
        fix_cx_cy,
        n_distortion_coefs
    )

    camera_matrix = np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)

    projected, _ = cv2.projectPoints(
        robot_points,
        rvec,
        tvec,
        camera_matrix,
        distortion
    )

    return projected.reshape(-1, 2)


def residuals(params: np.ndarray,
              robot_points: np.ndarray,
              measured_image_points: np.ndarray,
              image_size: tuple = (2500, 2000),
              fix_cx_cy: bool = False,
              n_distortion_coefs: int = 5,
              whitening: np.ndarray | None = None) -> np.ndarray:
    """
        Return x/y reprojection error for all measurements.
    :param params:
    :param robot_points:
    :param measured_image_points:
    :param image_size:
    :param fix_cx_cy:
    :param n_distortion_coefs:
    :param whitening: optional (N, 2, 2) matrices that standardise each residual
    :return:
    """

    predicted = project_points(
        params,
        robot_points,
        image_size=image_size,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )

    error = predicted - measured_image_points

    if whitening is not None:
        error = np.einsum("nij,nj->ni", whitening, error)

    return np.ravel(error)


def get_calibration(params: np.ndarray,
                    image_size_xy: tuple = (2500, 2000),
                    fix_cx_cy: bool = False,
                    n_distortion_coefs: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:

    fx, fy, cx, cy, distortion, rot_vec, tra_vec = unwrap_params(
        params,
        image_size=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )

    rotation_matrix, _ = cv2.Rodrigues(rot_vec)

    intrinsic_matrix = np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0]
    ])

    extrinsic_matrix = np.eye(4)
    extrinsic_matrix[:3, :3] = rotation_matrix
    extrinsic_matrix[:3, 3] = tra_vec.reshape(3)

    return intrinsic_matrix, distortion, rot_vec, extrinsic_matrix
