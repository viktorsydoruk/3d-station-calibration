# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""End-to-end synthetic calibration tests with a known camera model.

The apparent-centre correction, the home-position shift, and the least-squares
fit are exercised together on a scene that can be generated exactly: a grid of
spheres in the robot frame is rendered as tangent-cone silhouettes, the
detector-like circle fit supplies the measured centres, and the pipeline must
recover the ground-truth intrinsics and extrinsics.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from station_calibration import DebugInfo, Settings, get_calibration_data

_IMAGE_SIZE_XY = (2448, 2048)
_INTRINSIC = np.array(
    [
        [2500.0, 0.0, 1224.0],
        [0.0, 2500.0, 1024.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)
# Robot convention used by the initial-rotation estimate: +X toward the camera,
# +Y right in the image, +Z up in the image.
_ROTATION = np.array(
    [
        [0.0, 1.0, 0.0],
        [0.0, 0.0, -1.0],
        [-1.0, 0.0, 0.0],
    ],
    dtype=np.float64,
)
_TRANSLATION = np.array([0.0, 0.0, 300.0], dtype=np.float64)
_ROTATION_VECTOR, _ = cv2.Rodrigues(_ROTATION)
_SPHERE_RADIUS = 15.0

# Symmetric grid: 7 depth levels keep the quartic blur-fit well conditioned.
_ROBOT_POSITIONS = np.array(
    np.meshgrid(
        [-30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0],
        [-80.0, -40.0, 0.0, 40.0, 80.0],
        [-60.0, 0.0, 60.0],
        indexing="ij",
    )
).reshape(3, -1).T

_RADIAL_DISTORTION = np.zeros(14, dtype=np.float64)
_RADIAL_DISTORTION[0] = -0.1
_RADIAL_DISTORTION[1] = 0.02


def _silhouette_normalized(center_cam: np.ndarray,
                           radius: float,
                           n_points: int = 360) -> np.ndarray:
    """Tangent-cone silhouette of a sphere on the camera's z=1 plane."""
    distance = float(np.linalg.norm(center_cam))
    axis = center_cam / distance
    half_angle = np.arcsin(radius / distance)

    reference = np.array([1.0, 0.0, 0.0])
    if abs(axis[0]) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    basis_1 = np.cross(axis, reference)
    basis_1 /= np.linalg.norm(basis_1)
    basis_2 = np.cross(axis, basis_1)

    phi = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
    directions = (
        np.cos(half_angle) * axis[None, :]
        + np.sin(half_angle)
        * (
            np.cos(phi)[:, None] * basis_1[None, :]
            + np.sin(phi)[:, None] * basis_2[None, :]
        )
    )
    return directions[:, :2] / directions[:, 2:3]


def _project_normalized(points: np.ndarray,
                        distortion: np.ndarray) -> np.ndarray:
    homogeneous = np.concatenate(
        [np.asarray(points, dtype=np.float64), np.ones((len(points), 1))],
        axis=1,
    )
    projected, _ = cv2.projectPoints(
        homogeneous,
        np.zeros(3),
        np.zeros(3),
        _INTRINSIC,
        distortion,
    )
    return projected.reshape(-1, 2)


def _fit_circle(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    matrix = np.column_stack([x, y, np.ones_like(x)])
    rhs = -(x * x + y * y)
    d, e, f = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    center = np.array([-d / 2.0, -e / 2.0], dtype=np.float64)
    radius = float(np.sqrt(center[0] ** 2 + center[1] ** 2 - f))
    return center, radius


def _make_observations(distortion: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the measured centres, apparent radii, and blur sigmas."""
    centers = []
    radii = []
    sigmas = []
    for robot_point in _ROBOT_POSITIONS:
        camera_point = _ROTATION @ robot_point + _TRANSLATION
        silhouette = _project_normalized(
            _silhouette_normalized(camera_point, _SPHERE_RADIUS),
            distortion,
        )
        center, radius = _fit_circle(silhouette[:, 0], silhouette[:, 1])
        centers.append(center)
        radii.append(radius)
        # Defocus-like blur with a minimum at the home depth (robot X = 0).
        sigmas.append(2.0 + 0.001 * robot_point[0] ** 2)
    return np.asarray(centers), np.asarray(radii), np.asarray(sigmas)


def _settings(tmp_path, *, n_distortion_coefs: int) -> Settings:
    return Settings(
        tmp_path,
        debug=False,
        n_iterations=4,
        center_shift_tolerance=0.01,
        allowed_outliers=0,
        fix_cx_cy=True,
        n_distortion_coefs=n_distortion_coefs,
        focal_length_initial=2400.0,
        camera_distance_initial=280.0,
    )


def _run_pipeline(tmp_path, distortion: np.ndarray, n_distortion_coefs: int):
    centers, radii, sigmas = _make_observations(distortion)
    return get_calibration_data(
        _ROBOT_POSITIONS,
        centers,
        radii,
        sigmas,
        _IMAGE_SIZE_XY,
        _settings(tmp_path, n_distortion_coefs=n_distortion_coefs),
        DebugInfo(False),
    )


def test_synthetic_observation_is_offset_from_the_projected_centre() -> None:
    centers, radii, _ = _make_observations(np.zeros(14))
    projected, _ = cv2.projectPoints(
        _ROBOT_POSITIONS,
        _ROTATION_VECTOR,
        _TRANSLATION,
        _INTRINSIC,
        np.zeros(14),
    )
    offsets = np.linalg.norm(centers - projected.reshape(-1, 2), axis=1)

    # The correction must be large enough that the fit exercises it, but well
    # below the sphere radius.
    assert offsets.mean() > 0.5
    assert offsets.max() < radii.min()


def test_synthetic_pinhole_calibration_recovers_the_camera(tmp_path) -> None:
    distortion = np.zeros(14)
    result = _run_pipeline(tmp_path, distortion, n_distortion_coefs=0)

    pos_home, center_points, intrinsic, extrinsic, fitted_distortion, optimize_result, rmse, mask, n_dist = result
    assert int(mask.sum()) == len(_ROBOT_POSITIONS)
    assert n_dist == 0
    assert optimize_result.success
    assert len(optimize_result.x) == 8
    assert np.all(fitted_distortion == 0.0)

    assert np.linalg.norm(pos_home) < 0.1
    np.testing.assert_allclose(
        [intrinsic[0, 0], intrinsic[1, 1]],
        [_INTRINSIC[0, 0], _INTRINSIC[1, 1]],
        rtol=1e-3,
    )
    assert intrinsic[0, 2] == _INTRINSIC[0, 2]
    assert intrinsic[1, 2] == _INTRINSIC[1, 2]
    np.testing.assert_allclose(
        extrinsic[:3, 3],
        _TRANSLATION,
        atol=0.1,
    )
    fitted_rotation, _ = cv2.Rodrigues(extrinsic[:3, :3])
    rotation_error = np.degrees(np.linalg.norm(
        fitted_rotation.ravel() - _ROTATION_VECTOR.ravel()
    ))
    assert rotation_error < 0.01
    assert rmse < 0.1

    measured, _, _ = _make_observations(distortion)
    assert np.mean(np.linalg.norm(center_points - measured, axis=1)) > 0.5


def test_synthetic_distorted_calibration_recovers_the_camera(tmp_path) -> None:
    result = _run_pipeline(tmp_path, _RADIAL_DISTORTION, n_distortion_coefs=4)

    pos_home, center_points, intrinsic, extrinsic, fitted_distortion, optimize_result, rmse, mask, n_dist = result
    assert int(mask.sum()) == len(_ROBOT_POSITIONS)
    assert n_dist == 4
    assert optimize_result.success
    assert len(optimize_result.x) == 12

    assert np.linalg.norm(pos_home) < 0.1
    np.testing.assert_allclose(
        [intrinsic[0, 0], intrinsic[1, 1]],
        [_INTRINSIC[0, 0], _INTRINSIC[1, 1]],
        rtol=1e-3,
    )
    np.testing.assert_allclose(
        extrinsic[:3, 3],
        _TRANSLATION,
        atol=0.1,
    )
    fitted_rotation, _ = cv2.Rodrigues(extrinsic[:3, :3])
    rotation_error = np.degrees(np.linalg.norm(
        fitted_rotation.ravel() - _ROTATION_VECTOR.ravel()
    ))
    assert rotation_error < 0.01
    assert rmse < 0.1

    # k1/k2 are strongly correlated over this field of view, so compare the
    # radial scale itself; it is the quantity the data constrains.
    assert fitted_distortion[0] == pytest.approx(
        _RADIAL_DISTORTION[0], rel=0.05
    )
    np.testing.assert_allclose(
        fitted_distortion[2:4],
        np.zeros(2),
        atol=1e-3,
    )
    normalized_centers = (
        center_points - [_INTRINSIC[0, 2], _INTRINSIC[1, 2]]
    ) / [_INTRINSIC[0, 0], _INTRINSIC[1, 1]]
    radius = float(np.max(np.linalg.norm(normalized_centers, axis=1)))

    def radial_scale(coefficients: np.ndarray) -> float:
        r2 = radius * radius
        return (
            1.0
            + coefficients[0] * r2
            + coefficients[1] * r2 ** 2
            + coefficients[4] * r2 ** 3
        )

    assert radial_scale(fitted_distortion) == pytest.approx(
        radial_scale(_RADIAL_DISTORTION),
        abs=1e-3,
    )
    measured, _, _ = _make_observations(_RADIAL_DISTORTION)
    assert np.mean(np.linalg.norm(center_points - measured, axis=1)) > 0.5
