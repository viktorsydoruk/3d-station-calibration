# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the application service used by incremental frontends."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import station_calibration.service as service_module
from station_calibration import (
    CalibrationService,
    ImageAnalysisResult,
    Settings,
    SphereObservation,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path, debug=False, load_stored_data=False)


def test_service_analyzes_image_bytes_and_feeds_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    captured = {}

    def fake_analyze(image_bytes, **kwargs):
        captured["image_bytes"] = image_bytes
        captured["kwargs"] = kwargs
        return ImageAnalysisResult(
            observation=SphereObservation(600.0, 650.0, 12.0, 1.5),
            direction=1,
            image_shape=(900, 1200),
        )

    monkeypatch.setattr(service_module, "analyze_image_bytes", fake_analyze)

    service = CalibrationService(settings, fit_every_n=None)
    result = service.add_image_bytes(
        b"encoded-image",
        np.array([1.0, 2.0, 3.0]),
        source="camera-1",
    )

    assert result is None
    assert service.session.n_observations == 1
    observation = service.session.observations[0]
    assert observation.robot_position.tolist() == [1.0, 2.0, 3.0]
    assert observation.image_center.tolist() == [600.0, 650.0]
    assert observation.source == "camera-1"

    assert captured["image_bytes"] == b"encoded-image"
    assert captured["kwargs"]["bg_height_px"] == settings.bg_height_pxs
    assert captured["kwargs"]["bg_color_est_perc"] == settings.bg_color_est_perc
    assert captured["kwargs"]["image_index"] == 0
    assert captured["kwargs"]["debug_imagefile"] == settings.debug_folder / "ice_0000.png"
    assert captured["kwargs"]["print_debug"] is service.print_debug


def test_service_analyzes_image_array_and_feeds_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    captured = {}
    image = np.zeros((4, 4, 3), dtype=np.uint8)

    def fake_split(image_array):
        captured["image"] = image_array
        return image_array, None

    def fake_analyze(image_gray, image_color, **kwargs):
        captured["image_gray"] = image_gray
        captured["image_color"] = image_color
        captured["kwargs"] = kwargs
        return ImageAnalysisResult(
            observation=SphereObservation(600.0, 650.0, 12.0, 1.5),
            direction=1,
            image_shape=(4, 4),
        )

    monkeypatch.setattr(service_module, "split_image", fake_split)
    monkeypatch.setattr(service_module, "analyze_image", fake_analyze)

    service = CalibrationService(settings, fit_every_n=None)
    result = service.add_image_array(
        image,
        np.array([1.0, 2.0, 3.0]),
        source="camera-1",
    )

    assert result is None
    assert service.session.n_observations == 1
    observation = service.session.observations[0]
    assert observation.robot_position.tolist() == [1.0, 2.0, 3.0]
    assert observation.source == "camera-1"

    np.testing.assert_array_equal(captured["image"], image)
    assert captured["image_color"] is None
    assert captured["kwargs"]["image_index"] == 0
    assert captured["kwargs"]["debug_imagefile"] == settings.debug_folder / "ice_0000.png"
    assert captured["kwargs"]["print_debug"] is service.print_debug


def test_service_tracks_rejected_image_arrays(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    def fake_split(image_array):
        return image_array, None

    def fake_analyze(image_gray, image_color, **kwargs):
        return ImageAnalysisResult(
            observation=None,
            direction=0,
            image_shape=(4, 4),
            reason="direction is undefined",
        )

    monkeypatch.setattr(service_module, "split_image", fake_split)
    monkeypatch.setattr(service_module, "analyze_image", fake_analyze)

    service = CalibrationService(settings, fit_every_n=None)
    service.add_image_array(np.zeros((4, 4, 3), np.uint8), np.zeros(3), source="camera-1")
    service.add_image_array(np.zeros((4, 4, 3), np.uint8), np.zeros(3), source="camera-1")

    assert service.session.n_observations == 0
    assert service.session.n_rejections == 2
    assert service.session.rejections[0].reason == "direction is undefined"
    assert service.session.rejections[1].source == "camera-1"


def test_service_tracks_rejected_images(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    def fake_analyze(image_bytes, **kwargs):
        return ImageAnalysisResult(
            observation=None,
            direction=0,
            image_shape=(900, 1200),
            reason="direction is undefined",
        )

    monkeypatch.setattr(service_module, "analyze_image_bytes", fake_analyze)

    service = CalibrationService(settings, fit_every_n=None)
    service.add_image_bytes(b"first", np.zeros(3), source="camera-1")
    service.add_image_bytes(b"second", np.zeros(3), source="camera-1")

    assert service.session.n_observations == 0
    assert service.session.n_rejections == 2
    assert service.session.rejections[0].reason == "direction is undefined"
    assert service.session.rejections[1].source == "camera-1"


def test_service_turns_analysis_exception_into_rejection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(service_module, "split_image", lambda image: (image, None))

    def fake_analyze(image_gray, image_color, **kwargs):
        raise RuntimeError("bad frame")

    monkeypatch.setattr(service_module, "analyze_image", fake_analyze)

    service = CalibrationService(settings, fit_every_n=None)
    result = service.add_image_array(
        np.zeros((4, 4), dtype=np.uint8),
        np.zeros(3),
        source="camera-1",
    )

    assert result is None
    assert service.session.n_observations == 0
    assert service.session.n_rejections == 1
    rejection = service.session.rejections[0]
    assert "image analysis failed" in rejection.reason
    assert "RuntimeError" in rejection.reason
    assert "bad frame" in rejection.reason
    assert rejection.source == "camera-1"


def test_service_delegates_readiness_and_stop_request(tmp_path: Path) -> None:
    service = CalibrationService(_settings(tmp_path), fit_every_n=None)

    assert service.is_ready is False
    service.request_stop("operator finished")
    assert service.is_ready is False  # minimum observations are still required
    assert service.stop_detail is not None
    assert "operator finished" in service.stop_detail
