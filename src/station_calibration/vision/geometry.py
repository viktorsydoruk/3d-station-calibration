# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Image-point geometry helpers."""

__all__ = [
    "adjust_image_center_points",
]

import numpy as np


def adjust_image_center_points(image_center_points: np.ndarray,
                               radii: np.ndarray,
                               intrinsic_matrix: np.ndarray,
                               ) -> np.ndarray:
    """
        Adjust the center points of spheres using radii and intrinsic matrix. The equation delievered using
        Angle bisector theorem
    :param image_center_points: center points of spheres on the images taken
    :param radii: visual radii of the sphere with bluring
    :param intrinsic_matrix: intrinsic matrix of the camera
    :return: new center points of sphere
    """
    # camera principal point
    c_xy = np.array([intrinsic_matrix[0, 2], intrinsic_matrix[1, 2]])[None, :]

    # points with added radii
    xy_plus = image_center_points + radii[:, None]
    # points with subtracted radii
    xy_minus = image_center_points - radii[:, None]

    # focal distances
    f_xy = np.array([intrinsic_matrix[0, 0], intrinsic_matrix[1, 1]])[None, :]

    # distance ratio used in angle bisector theorem
    dist_ratio = np.sqrt(((c_xy - xy_plus) ** 2 + f_xy ** 2) / ((c_xy - xy_minus) ** 2 + f_xy ** 2))

    # calculation of new center points
    new_image_center_points = image_center_points + radii[:, None] * (1 - dist_ratio) / (1 + dist_ratio)

    return new_image_center_points
