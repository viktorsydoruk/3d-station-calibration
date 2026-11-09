# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the folder source adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

import station_calibration.sources.folder as folder_module
import station_calibration.session as session_module
from station_calibration import (
    DebugInfo,
    FolderCalibrationSource,
    ImageAnalysisResult,
    Settings,
    SphereObservation,
    create_folder_session,
    get_3D_and_2D_data,
    get_calibration_data,
    load_all_points,
    load_all_points_with_covariances,
    observations_to_arrays,
)


DATA_FILE = Path(__file__).parent / "data" / "CalibrationAllPoints.dat"


def _settings(tmp_path: Path, **overrides) -> Settings:
    options = {
        "debug": False,
        "n_iterations": 1,
        "allowed_outliers": 0,
        "n_distortion_coefs": 4,
        "focal_length_initial": 2000.0,
        "camera_distance_initial": 80.0,
        "target_observations": 100,
    }
    options.update(overrides)
    return Settings(tmp_path, **options)


def test_stored_cache_source_matches_direct_fit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    shutil.copy(DATA_FILE, settings.all_center_points_file)

    source = FolderCalibrationSource(settings, DebugInfo(False))
    dataset = source.load()

    assert dataset.from_stored_data is True
    assert dataset.apply_radius_filter is False
    assert len(dataset.observations) == 492
    assert len(dataset.fit_observations) == 492
    assert len(dataset.rejections) == 8
    assert dataset.image_size_xy == (2448, 2048)

    session = create_folder_session(settings, DebugInfo(False), fit_every_n=None)
    assert session.apply_radius_filter is False
    assert session.n_observations == 492
    assert session.n_rejections == 8
    assert session.image_size_xy == (2448, 2048)

    result = session.finish()

    robot_positions, center_points, radii, sigmas, image_sizes, directions = (
        load_all_points(DATA_FILE)
    )
    valid = np.logical_and(~np.isnan(sigmas), ~np.isnan(radii))
    image_size_xy = np.flip(np.nanmax(image_sizes, axis=0)).astype(int).tolist()
    direct = get_calibration_data(
        robot_positions[valid],
        center_points[valid],
        radii[valid],
        sigmas[valid],
        image_size_xy,
        settings,
        DebugInfo(False),
    )

    assert result.observation_count == 492
    assert result.n_used == 492
    assert result.image_size_xy == (2448, 2048)
    np.testing.assert_allclose(result.pos_home, direct[0], rtol=1e-6, atol=1e-4)
    np.testing.assert_allclose(
        result.intrinsic_matrix, direct[2], rtol=1e-7, atol=1e-8
    )
    np.testing.assert_allclose(
        result.extrinsic_matrix, direct[3], rtol=1e-5, atol=1e-7
    )
    np.testing.assert_allclose(result.distortion, direct[4], rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(
        result.optimize_result.x, direct[5].x, rtol=1e-5, atol=1e-6
    )
    assert result.rmse == pytest.approx(direct[6], rel=1e-6)


def test_get_3d_and_2d_data_uses_folder_source(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    shutil.copy(DATA_FILE, settings.all_center_points_file)

    dataset = FolderCalibrationSource(settings, DebugInfo(False)).load()
    expected = observations_to_arrays(dataset.fit_observations)
    actual = get_3D_and_2D_data(settings, DebugInfo(False))

    for actual_array, expected_array in zip(actual[:5], expected):
        np.testing.assert_allclose(actual_array, expected_array)
    assert tuple(actual[5]) == dataset.image_size_xy


def test_fresh_source_feeds_raw_observations_and_session_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, load_stored_data=False)
    n_images = 17
    robot_positions = np.column_stack(
        [
            np.linspace(0.0, 160.0, n_images),
            np.linspace(0.0, 80.0, n_images),
            np.linspace(10.0, 90.0, n_images),
        ]
    )
    image_filenames = [tmp_path / f"image_{index:02d}.tif" for index in range(n_images)]

    covariance = np.array([[0.01, 0.001], [0.001, 0.02]])
    analyses = []
    for index in range(n_images):
        if index == n_images - 1:
            analyses.append(
                ImageAnalysisResult(
                    observation=None,
                    direction=0,
                    image_shape=(900, 1200),
                    reason="direction is undefined",
                )
            )
            continue

        radius = 100.0 if index == n_images - 2 else 12.0
        analyses.append(
            ImageAnalysisResult(
                observation=SphereObservation(
                    600.0 + index,
                    650.0 + index,
                    radius,
                    2.0,
                    center_covariance=covariance,
                ),
                direction=1,
                image_shape=(900, 1200),
            )
        )

    monkeypatch.setattr(
        folder_module,
        "load_robot_positions",
        lambda path: (robot_positions, [path.name for path in image_filenames]),
    )
    monkeypatch.setattr(
        folder_module,
        "search_images",
        lambda *args, **kwargs: image_filenames,
    )
    monkeypatch.setattr(
        folder_module,
        "analyze_images",
        lambda *args, **kwargs: analyses,
    )

    source = FolderCalibrationSource(settings, DebugInfo(False))
    dataset = source.load()

    assert dataset.from_stored_data is False
    assert dataset.apply_radius_filter is True
    assert len(dataset.observations) == 16
    assert len(dataset.fit_observations) == 15
    assert len(dataset.rejections) == 1
    assert dataset.image_size_xy == (1200, 900)

    # The cache keeps the folder workflow's NaN rows, including the radius outlier.
    stored = load_all_points(settings.all_center_points_file)
    assert len(stored[0]) == n_images
    assert np.isnan(stored[2][n_images - 2])
    assert np.isnan(stored[2][n_images - 1])
    assert stored[2][0] == pytest.approx(12.0)

    stored_with_covariance = load_all_points_with_covariances(
        settings.all_center_points_file
    )
    np.testing.assert_allclose(stored_with_covariance[6][0], covariance)
    assert np.all(np.isnan(stored_with_covariance[6][n_images - 2]))

    session = source.open_session(fit_every_n=None)
    assert session.n_observations == 16
    assert session.n_rejections == 1
    assert session.apply_radius_filter is True

    captured = {}

    def fake_get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        settings,
        print_debug,
        *,
        center_covariances=None,
    ):
        captured["n_points"] = len(robot_positions)
        captured["center_covariances"] = center_covariances
        return (
            np.mean(robot_positions, axis=0),
            np.array(center_points, copy=True),
            np.eye(3),
            np.eye(4),
            np.zeros(14),
            OptimizeResult(
                x=np.zeros(8),
                fun=np.zeros(2 * len(robot_positions)),
                success=True,
                cost=0.0,
                message="fake",
            ),
            0.0,
            np.ones(len(robot_positions), dtype=bool),
            0,
        )

    monkeypatch.setattr(
        session_module,
        "get_calibration_data",
        fake_get_calibration_data,
    )

    result = session.finish()

    assert captured["n_points"] == 15
    assert captured["center_covariances"] is not None
    assert captured["center_covariances"].shape == (15, 2, 2)
    np.testing.assert_allclose(captured["center_covariances"][0], covariance)
    assert result.observation_count == 16
    assert result.n_used == 15
    assert result.image_size_xy == (1200, 900)
    assert len(session.fit_observations) == 15
