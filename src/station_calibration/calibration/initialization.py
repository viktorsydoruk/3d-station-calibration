# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Initial robot-to-camera estimate and parameter packing."""

__all__ = [
    "estimate_r_initial",
    "extract_z_lines",
    "make_initial_parameters",
]

import cv2
import numpy as np

from ..support import fit_line_general_form, intersect_lines


def _orthonormalize_rotation(matrix: np.ndarray) -> np.ndarray:
    """Return the closest proper rotation matrix to ``matrix``.

    The correlation matrix used as an initial estimate is not guaranteed to be
    orthogonal. A polar decomposition via SVD gives the closest orthogonal
    matrix; the determinant correction removes reflections.
    """
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        return np.eye(3, dtype=np.float64)

    try:
        u, _, vt = np.linalg.svd(matrix)
    except np.linalg.LinAlgError:
        return np.eye(3, dtype=np.float64)

    rotation = u @ vt
    if np.linalg.det(rotation) < 0.0:
        u = u.copy()
        u[:, -1] *= -1.0
        rotation = u @ vt
    return rotation


def estimate_r_initial(robot_positions: np.ndarray,
                       image_center_points: np.ndarray,
                       radii: np.ndarray,
                       sigmas: np.ndarray) -> np.ndarray:
    """
        Estimation of initial robot-camera rotation matrix using positions of robotic arm and center points on images

        ChatGPT generated such a constant:
        ============================================================
        Robot -> camera initial rotation

        Robot:
          +X = toward camera
          +Y = right in image
          +Z = up in image

        OpenCV camera:
          +X = right
          +Y = down
          +Z = away from camera

        Therefore:

          Xc =  Yr
          Yc =  Zr
          Zc = -Xr
        ============================================================
        R_INITIAL = np.array([
            [0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0],
            [-1.0, 0.0, 0.0],
        ], dtype=np.float64)

    :param robot_positions: positions of a nozzle by robotic arm
    :param image_center_points: center points of spheres on the images
    :param radii: radii of spheres
    :param sigmas: bluring sigmas of spheres edges
    :return: 3x3 rotation matrix
    """
    robot_positions = np.asarray(robot_positions, dtype=np.float64)
    image_center_points = np.asarray(image_center_points, dtype=np.float64)
    radii = np.asarray(radii, dtype=np.float64).reshape(-1)
    sigmas = np.asarray(sigmas, dtype=np.float64).reshape(-1)

    n_points = len(robot_positions)
    if (
        n_points < 3
        or robot_positions.shape != (n_points, 3)
        or image_center_points.shape != (n_points, 2)
        or radii.shape != (n_points,)
        or sigmas.shape != (n_points,)
    ):
        return np.eye(3, dtype=np.float64)

    camera_points = np.column_stack(
        (image_center_points, -(radii - 2.0 * sigmas))
    )
    if (
        not np.all(np.isfinite(camera_points))
        or not np.all(np.isfinite(robot_positions))
        or np.any(np.ptp(camera_points, axis=0) == 0.0)
        or np.any(np.ptp(robot_positions, axis=0) == 0.0)
    ):
        return np.eye(3, dtype=np.float64)

    # Just use the correlation coefficients as the initial estimate, then
    # project them onto the nearest proper rotation.
    r_initial = np.corrcoef(camera_points.T, robot_positions.T)[:3, 3:]
    return _orthonormalize_rotation(r_initial)


def extract_z_lines(robot_positions: np.ndarray,
                    image_center_points: np.ndarray,
                    r_initial: np.ndarray) -> np.ndarray:
    z_arg = np.argwhere(r_initial[2] != 0)[0][0]
    left_args = [0, 1, 2]
    left_args.remove(z_arg)

    lines: list[list[float]] = []
    left_robot_positions = np.copy(robot_positions)
    left_image_center_points = np.copy(image_center_points)
    while len(left_robot_positions) != 0:
        sel_args = np.argwhere((left_robot_positions[:, left_args[0]] == left_robot_positions[0, left_args[0]])
                               & (left_robot_positions[:, left_args[1]] == left_robot_positions[0, left_args[1]])).flatten()
        if len(sel_args) > 3:
            a, b, c = fit_line_general_form(*left_image_center_points[sel_args].T)

            lines.append([a, b, c])
        left_robot_positions = np.delete(left_robot_positions, sel_args, axis=0)
        left_image_center_points = np.delete(left_image_center_points, sel_args, axis=0)

    all_intersection_points: list[tuple[float, float]] = []
    for i in range(len(lines)):
        for j in range(i, len(lines)):
            int_point = intersect_lines(*lines[i], *lines[j])
            if int_point is not None and int_point[0] > 0 and int_point[1] > 0 and int_point[0] < 2500 and int_point[1] < 2000:
                all_intersection_points.append(int_point)

    intersection_points = np.array(all_intersection_points)
    return np.mean(intersection_points, axis=0)


def make_initial_parameters(focal_length: float = 2000.0,
                            camera_distance: float = 80.0,
                            image_size: tuple = (2500, 2000),
                            fix_cx_cy: bool = False,
                            n_distortion_coefs: int = 5,
                            r_initial: np.ndarray = np.eye(3)) -> np.ndarray:
    """
        Create initial parameter vector.

        camera_distance is only used as an approximate initial
        translation. It may need adjustment depending on the
        robot coordinate origin.

    :param focal_length:
    :param camera_distance:
    :param image_size:
    :param fix_cx_cy:
    :param n_distortion_coefs:
    :param r_initial:
    :return:
    """

    params = np.empty(0, dtype=np.float64)

    # intrinsics
    params = np.append(params, (focal_length, focal_length))  # fx and fy
    if not fix_cx_cy:
        params = np.append(params, (image_size[0] / 2, image_size[1] / 2))  # cx, cy if needed

    # distortion
    params = np.append(params, (0,) * n_distortion_coefs)

    # initial rotation
    rvecs_initial, _ = cv2.Rodrigues(_orthonormalize_rotation(r_initial))
    params = np.append(params, rvecs_initial.ravel())

    # initial translation
    params = np.append(params, (0, 0, camera_distance))

    return params
