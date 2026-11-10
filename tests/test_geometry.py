# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the apparent-centre correction of projected spheres."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from station_calibration.vision.geometry import adjust_image_center_points

_INTRINSIC = np.array(
    [
        [2500.0, 0.0, 1224.0],
        [0.0, 2500.0, 1024.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)

_ZERO_DISTORTION = np.zeros(14, dtype=np.float64)

# A realistic radial model: barrel distortion at the centre that becomes
# slightly compressive towards the image border.
_RADIAL_DISTORTION = np.zeros(14, dtype=np.float64)
_RADIAL_DISTORTION[0] = -0.15
_RADIAL_DISTORTION[1] = 0.05


def _silhouette_normalized(center: np.ndarray,
                           radius: float,
                           n_points: int = 1440) -> np.ndarray:
    """Return the tangent-cone silhouette of a sphere on the z=1 plane."""
    center = np.asarray(center, dtype=np.float64)
    distance = float(np.linalg.norm(center))
    axis = center / distance
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
                        intrinsic_matrix: np.ndarray,
                        distortion: np.ndarray) -> np.ndarray:
    homogeneous = np.concatenate(
        [np.asarray(points, dtype=np.float64), np.ones((len(points), 1))],
        axis=1,
    )
    projected, _ = cv2.projectPoints(
        homogeneous,
        np.zeros(3),
        np.zeros(3),
        intrinsic_matrix,
        distortion,
    )
    return projected.reshape(-1, 2)


def _project_points(points: np.ndarray,
                    intrinsic_matrix: np.ndarray,
                    distortion: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    projected, _ = cv2.projectPoints(
        points,
        np.zeros(3),
        np.zeros(3),
        intrinsic_matrix,
        distortion,
    )
    return projected.reshape(-1, 2)


def _fit_circle(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Kasa circle fit, matching the detector's apparent-centre estimate."""
    matrix = np.column_stack([x, y, np.ones_like(x)])
    rhs = -(x * x + y * y)
    d, e, f = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    center = np.array([-d / 2.0, -e / 2.0], dtype=np.float64)
    radius = float(np.sqrt(center[0] ** 2 + center[1] ** 2 - f))
    return center, radius


def _synthetic_observation(center: np.ndarray,
                           radius: float,
                           intrinsic_matrix: np.ndarray = _INTRINSIC,
                           distortion: np.ndarray = _ZERO_DISTORTION,
                           ) -> tuple[np.ndarray, float, np.ndarray]:
    """Return the measured circle and the true projected sphere centre."""
    silhouette = _silhouette_normalized(center, radius)
    image_points = _project_normalized(silhouette, intrinsic_matrix, distortion)
    measured_center, measured_radius = _fit_circle(
        image_points[:, 0],
        image_points[:, 1],
    )
    true_center = _project_points(
        np.asarray(center, dtype=np.float64)[None, :],
        intrinsic_matrix,
        distortion,
    )[0]
    return measured_center, measured_radius, true_center


def test_rejects_non_2d_center_points() -> None:
    with pytest.raises(ValueError, match="image_center_points"):
        adjust_image_center_points(np.zeros((3, 3)), np.ones(3), _INTRINSIC)
    with pytest.raises(ValueError, match="image_center_points"):
        adjust_image_center_points(np.zeros(3), np.ones(3), _INTRINSIC)


def test_rejects_radii_length_mismatch() -> None:
    with pytest.raises(ValueError, match="radii"):
        adjust_image_center_points(np.zeros((3, 2)), np.ones(2), _INTRINSIC)


@pytest.mark.parametrize("bad_radius", [-1.0, np.nan, np.inf])
def test_rejects_invalid_radii(bad_radius: float) -> None:
    with pytest.raises(ValueError, match="radii"):
        adjust_image_center_points(
            np.zeros((1, 2)),
            np.array([bad_radius]),
            _INTRINSIC,
        )


def test_rejects_non_3x3_intrinsic_matrix() -> None:
    with pytest.raises(ValueError, match="intrinsic_matrix"):
        adjust_image_center_points(np.zeros((1, 2)), np.ones(1), np.eye(2))


def test_rejects_non_finite_distortion() -> None:
    distortion = np.zeros(5)
    distortion[0] = np.nan
    with pytest.raises(ValueError, match="distortion"):
        adjust_image_center_points(
            np.zeros((1, 2)),
            np.ones(1),
            _INTRINSIC,
            distortion,
        )


def test_empty_input_returns_empty() -> None:
    empty = np.empty((0, 2), dtype=np.float64)
    result = adjust_image_center_points(empty, np.empty(0), _INTRINSIC)
    assert result.shape == (0, 2)


@pytest.mark.parametrize("radius", [0.0, 5.0, 150.0])
@pytest.mark.parametrize("distortion", [None, _RADIAL_DISTORTION])
def test_point_at_the_principal_point_is_unchanged(radius: float,
                                                   distortion: np.ndarray | None) -> None:
    principal_point = _INTRINSIC[:2, 2][None, :]
    result = adjust_image_center_points(
        principal_point,
        np.array([radius]),
        _INTRINSIC,
        distortion,
    )
    np.testing.assert_allclose(result, principal_point, atol=1e-9)


@pytest.mark.parametrize(
    "point",
    [(600.0, 500.0), (1800.0, 1500.0), (300.0, 1600.0)],
)
def test_zero_radius_is_unchanged(point: tuple[float, float]) -> None:
    centers = np.array([point], dtype=np.float64)
    result = adjust_image_center_points(centers, np.zeros(1), _INTRINSIC)
    np.testing.assert_allclose(result, centers, atol=1e-12)


def test_correction_moves_points_toward_the_principal_point() -> None:
    centers = np.array(
        [
            [1624.0, 1324.0],  # right and below the principal point
            [824.0, 724.0],  # left and above the principal point
        ],
        dtype=np.float64,
    )
    radii = np.array([100.0, 100.0])
    result = adjust_image_center_points(centers, radii, _INTRINSIC)
    shift = result - centers

    assert np.all(shift[0] < 0.0)
    assert np.all(shift[1] > 0.0)
    assert np.all(np.abs(shift) <= radii[:, None])


def test_symmetric_points_get_symmetric_corrections() -> None:
    offset = np.array([400.0, 300.0])
    principal_point = _INTRINSIC[:2, 2]
    centers = np.stack(
        [principal_point + offset, principal_point - offset]
    )
    radii = np.array([120.0, 120.0])
    result = adjust_image_center_points(centers, radii, _INTRINSIC)
    shift = result - centers

    np.testing.assert_allclose(shift[0], -shift[1], atol=1e-10)


@pytest.mark.parametrize(
    "center",
    [
        (0.0, 0.0, 80.0),
        (20.0, 0.0, 80.0),
        (0.0, 25.0, 80.0),
        (30.0, 25.0, 80.0),
        (35.0, -30.0, 85.0),
        (-38.0, 32.0, 75.0),
    ],
)
def test_synthetic_sphere_recovers_the_projected_centre(center: tuple[float, float, float]) -> None:
    center = np.asarray(center, dtype=np.float64)
    measured, radius, true_center = _synthetic_observation(center, 5.0)
    raw_error = np.linalg.norm(measured - true_center)

    adjusted = adjust_image_center_points(
        measured[None, :],
        np.array([radius]),
        _INTRINSIC,
    )[0]
    adjusted_error = np.linalg.norm(adjusted - true_center)

    assert adjusted_error < 0.5
    assert adjusted_error < 0.2 * raw_error + 1e-6


@pytest.mark.parametrize(
    "center",
    [
        (20.0, 0.0, 80.0),
        (0.0, 25.0, 80.0),
        (30.0, 25.0, 80.0),
        (35.0, -30.0, 85.0),
        (-38.0, 32.0, 75.0),
    ],
)
def test_synthetic_sphere_with_distortion_recovers_the_projected_centre(
    center: tuple[float, float, float],
) -> None:
    center = np.asarray(center, dtype=np.float64)
    measured, radius, true_center = _synthetic_observation(
        center,
        5.0,
        distortion=_RADIAL_DISTORTION,
    )

    without_distortion = adjust_image_center_points(
        measured[None, :],
        np.array([radius]),
        _INTRINSIC,
    )[0]
    with_distortion = adjust_image_center_points(
        measured[None, :],
        np.array([radius]),
        _INTRINSIC,
        _RADIAL_DISTORTION,
    )[0]

    distorted_error = np.linalg.norm(with_distortion - true_center)
    undistorted_error = np.linalg.norm(without_distortion - true_center)

    assert distorted_error < 0.5
    assert distorted_error < 0.2 * undistorted_error


def test_zero_distortion_matches_the_pinhole_path() -> None:
    centers = np.array(
        [
            [600.0, 500.0],
            [1800.0, 1500.0],
            [1000.0, 1100.0],
        ],
        dtype=np.float64,
    )
    radii = np.array([80.0, 140.0, 30.0])

    pinhole = adjust_image_center_points(centers, radii, _INTRINSIC)
    explicit_zeros = adjust_image_center_points(
        centers,
        radii,
        _INTRINSIC,
        _ZERO_DISTORTION,
    )

    np.testing.assert_array_equal(pinhole, explicit_zeros)
