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
    camera_points = np.asarray([*image_center_points.T, -(radii-2*sigmas)]).T

    # just use correlation coef as r_initial
    r_initial = np.corrcoef(camera_points.T, robot_positions.T)[:3, 3:]

    return r_initial


def extract_z_lines(robot_positions: np.ndarray,
                    image_center_points: np.ndarray,
                    r_initial: np.ndarray) -> np.ndarray:
    z_arg = np.argwhere(r_initial[2] != 0)[0][0]
    left_args = [0, 1, 2]
    left_args.remove(z_arg)

    lines = []
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

    all_intersection_points = []
    for i in range(len(lines)):
        for j in range(i, len(lines)):
            int_point = intersect_lines(*lines[i], *lines[j])
            if int_point is not None and int_point[0] > 0 and int_point[1] > 0 and int_point[0] < 2500 and int_point[1] < 2000:
                all_intersection_points.append(int_point)

    all_intersection_points = np.array(all_intersection_points)
    return np.mean(all_intersection_points, axis=0)


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
    rvecs_initial, _ = cv2.Rodrigues(r_initial)
    params = np.append(params, rvecs_initial.ravel())

    # initial translation
    params = np.append(params, (0, 0, camera_distance))

    return params
