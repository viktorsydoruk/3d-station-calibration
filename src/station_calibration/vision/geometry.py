# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Image-point geometry helpers."""

__all__ = [
    "adjust_image_center_points",
]

import cv2
import numpy as np


def _undistort_to_normalized(points: np.ndarray,
                             intrinsic_matrix: np.ndarray,
                             distortion: np.ndarray) -> np.ndarray:
    """Map distorted pixel points to the undistorted normalised image plane."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    undistorted = cv2.undistortPoints(points, intrinsic_matrix, distortion)
    return undistorted.reshape(-1, 2)


def _distort_from_normalized(points: np.ndarray,
                             intrinsic_matrix: np.ndarray,
                             distortion: np.ndarray) -> np.ndarray:
    """Map points on the normalised image plane back to distorted pixels."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homogeneous = np.concatenate(
        [points, np.ones((points.shape[0], 1), dtype=np.float64)],
        axis=1,
    )
    projected, _ = cv2.projectPoints(
        homogeneous,
        np.zeros(3, dtype=np.float64),
        np.zeros(3, dtype=np.float64),
        intrinsic_matrix,
        distortion,
    )
    return projected.reshape(-1, 2)


def adjust_image_center_points(image_center_points: np.ndarray,
                               radii: np.ndarray,
                               intrinsic_matrix: np.ndarray,
                               distortion: np.ndarray | None = None,
                               ) -> np.ndarray:
    """
        Adjust the center points of spheres using radii and intrinsic matrix. The equation is derived using
        the angle bisector theorem
    :param image_center_points: center points of spheres on the images taken
    :param radii: visual radii of the sphere with blurring
    :param intrinsic_matrix: intrinsic matrix of the camera
    :param distortion: optional OpenCV distortion coefficients. When present, the
        correction is evaluated in the undistorted pinhole plane so that lens
        distortion does not bias the apparent-centre correction.
    :return: new center points of sphere
    """
    centers = np.asarray(image_center_points, dtype=np.float64)
    if centers.ndim != 2 or centers.shape[1] != 2:
        raise ValueError(
            f"image_center_points must have shape (N, 2), got {centers.shape}"
        )

    radii = np.asarray(radii, dtype=np.float64).reshape(-1)
    if radii.size != centers.shape[0]:
        raise ValueError(
            "radii must contain one value per center point, got "
            f"{radii.size} for {centers.shape[0]} points"
        )
    if not np.all(np.isfinite(radii)) or np.any(radii < 0.0):
        raise ValueError("radii must be finite and non-negative")

    intrinsic_matrix = np.asarray(intrinsic_matrix, dtype=np.float64)
    if intrinsic_matrix.shape != (3, 3):
        raise ValueError(
            f"intrinsic_matrix must have shape (3, 3), got {intrinsic_matrix.shape}"
        )

    if centers.shape[0] == 0:
        return centers.copy()

    # camera principal point
    c_xy = np.array([intrinsic_matrix[0, 2], intrinsic_matrix[1, 2]])[None, :]
    # focal distances
    f_xy = np.array([intrinsic_matrix[0, 0], intrinsic_matrix[1, 1]])[None, :]

    if distortion is None:
        distortion = np.zeros(14, dtype=np.float64)
    else:
        distortion = np.asarray(distortion, dtype=np.float64).reshape(-1)
        if not np.all(np.isfinite(distortion)):
            raise ValueError("distortion must contain only finite values")

    if not np.any(distortion):
        # Pinhole camera: the angle-bisector equation is evaluated directly in
        # pixel coordinates.
        # points with added radii
        xy_plus = centers + radii[:, None]
        # points with subtracted radii
        xy_minus = centers - radii[:, None]

        # distance ratio used in angle bisector theorem
        dist_ratio = np.sqrt(
            ((c_xy - xy_plus) ** 2 + f_xy ** 2)
            / ((c_xy - xy_minus) ** 2 + f_xy ** 2)
        )

        # calculation of new center points
        return centers + radii[:, None] * (1 - dist_ratio) / (1 + dist_ratio)

    # Build the four apparent extremes in distorted pixel coordinates: the two
    # horizontal and the two vertical silhouette borders.  The angle-bisector
    # relation is a pinhole relation, so it must be applied to the undistorted
    # image plane and the result mapped back to the measured (distorted) space.
    extremes = np.stack(
        [
            centers + radii[:, None] * np.array([1.0, 0.0]),
            centers - radii[:, None] * np.array([1.0, 0.0]),
            centers + radii[:, None] * np.array([0.0, 1.0]),
            centers - radii[:, None] * np.array([0.0, 1.0]),
        ],
        axis=1,
    )
    extremes = _undistort_to_normalized(
        extremes.reshape(-1, 2),
        intrinsic_matrix,
        distortion,
    ).reshape(-1, 4, 2)

    corrected = np.empty_like(extremes[:, 0])
    for axis, (index_plus, index_minus) in enumerate(((0, 1), (2, 3))):
        coord_plus = extremes[:, index_plus, axis]
        coord_minus = extremes[:, index_minus, axis]

        # distance ratio used in angle bisector theorem, in normalised units
        dist_ratio = np.sqrt(
            (1.0 + coord_plus ** 2) / (1.0 + coord_minus ** 2)
        )

        # foot of the angle bisector: the projection of the sphere centre
        corrected[:, axis] = (
            (coord_plus + dist_ratio * coord_minus) / (1.0 + dist_ratio)
        )

    return _distort_from_normalized(
        corrected,
        intrinsic_matrix,
        distortion,
    )
