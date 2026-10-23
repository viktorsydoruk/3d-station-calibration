"""Tests for single-image analysis and the batch wrapper."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

import station_calibration.image as image_module
from station_calibration import DebugInfo
from station_calibration.image import (
    analyze_image,
    analyze_image_bytes,
    decode_image,
    get_sphere_centers_and_blur_sigmas,
)


SYNTHETIC_CENTER = (600.0, 650.0)
SYNTHETIC_RADIUS = 170.0


def _synthetic_image() -> tuple[np.ndarray, np.ndarray]:
    """Create a deterministic nozzle-like scene with one blurred bright sphere."""
    height, width = 900, 1200
    image = np.zeros((height, width), dtype=np.uint8)

    # Textured top region and a bright nozzle-shaped area. This makes the
    # direction estimator choose +1 (nozzle at the top).
    rng = np.random.default_rng(0)
    image[:160] = rng.integers(0, 60, size=(160, width), dtype=np.uint8)
    cv2.rectangle(image, (520, 0), (680, 300), 180, -1)

    # Sphere in the lower portion of the image with a softly blurred edge.
    cv2.circle(
        image,
        (int(SYNTHETIC_CENTER[0]), int(SYNTHETIC_CENTER[1])),
        int(SYNTHETIC_RADIUS),
        220,
        -1,
        lineType=cv2.LINE_AA,
    )
    image = cv2.GaussianBlur(image, (0, 0), 2.5)

    return image, cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def _analysis_kwargs() -> dict:
    return {
        "bg_height_px": 200,
        "fixed_bg_threshold": 30,
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "min_bg_pixels_on_edges": 5,
        "blur_est_border_thickness": 2,
        "print_debug": DebugInfo(False),
    }


def test_decode_image_round_trip() -> None:
    _, color_image = _synthetic_image()
    success, encoded = cv2.imencode(".png", color_image)
    assert success

    image_gray, image_color = decode_image(encoded.tobytes())

    assert image_color.shape == color_image.shape
    assert image_gray.shape == color_image.shape[:2]
    np.testing.assert_array_equal(image_color, color_image)


def test_analyze_image_extracts_synthetic_sphere() -> None:
    image_gray, _ = _synthetic_image()

    result = analyze_image(image_gray, **_analysis_kwargs())

    assert result.reason is None
    assert result.direction == 1
    assert result.image_shape == image_gray.shape
    assert result.observation is not None

    observation = result.observation
    assert observation.x == pytest.approx(SYNTHETIC_CENTER[0], abs=2.0)
    assert observation.y == pytest.approx(SYNTHETIC_CENTER[1], abs=2.0)
    assert observation.radius == pytest.approx(SYNTHETIC_RADIUS, abs=5.0)
    assert observation.sigma == pytest.approx(2.5, abs=0.5)


def test_analyze_image_bytes_extracts_synthetic_sphere() -> None:
    _, color_image = _synthetic_image()
    success, encoded = cv2.imencode(".png", color_image)
    assert success

    result = analyze_image_bytes(encoded.tobytes(), **_analysis_kwargs())

    assert result.observation is not None
    assert result.observation.x == pytest.approx(SYNTHETIC_CENTER[0], abs=2.0)
    assert result.observation.y == pytest.approx(SYNTHETIC_CENTER[1], abs=2.0)


def test_analyze_image_reports_undefined_direction() -> None:
    image_gray = np.zeros((300, 400), dtype=np.uint8)

    result = analyze_image(
        image_gray,
        bg_height_px=100,
        fixed_bg_threshold=30,
        print_debug=DebugInfo(False),
    )

    assert result.observation is None
    assert result.direction == 0
    assert result.reason == "direction is undefined"


def test_analyze_image_reports_missing_sphere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_module, "estimate_direction", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        image_module, "get_forground_mask", lambda *args, **kwargs: np.zeros((300, 400), bool)
    )
    monkeypatch.setattr(
        image_module, "find_the_sphere_on_mask", lambda *args, **kwargs: None
    )

    result = analyze_image(
        np.zeros((300, 400), dtype=np.uint8),
        fixed_bg_threshold=30,
        print_debug=DebugInfo(False),
    )

    assert result.observation is None
    assert result.direction == 1
    assert result.reason == "sphere is not found or out of FOV"


def test_analyze_image_reports_missing_sigma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_module, "estimate_direction", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        image_module, "get_forground_mask", lambda *args, **kwargs: np.ones((300, 400), bool)
    )
    monkeypatch.setattr(
        image_module,
        "find_the_sphere_on_mask",
        lambda *args, **kwargs: (100.0, 200.0, 50.0),
    )
    monkeypatch.setattr(image_module, "get_blur_sigma", lambda *args, **kwargs: None)

    result = analyze_image(
        np.zeros((300, 400), dtype=np.uint8),
        fixed_bg_threshold=30,
        print_debug=DebugInfo(False),
    )

    assert result.observation is None
    assert result.direction == 1
    assert result.reason == "border sigma cannot be estimated"


def test_batch_analysis_uses_single_image_result(tmp_path: Path) -> None:
    _, color_image = _synthetic_image()
    image_path = tmp_path / "synthetic_sphere.png"
    assert cv2.imwrite(str(image_path), color_image)

    centers, sigmas, radii, image_sizes, directions = (
        get_sphere_centers_and_blur_sigmas(
            [image_path],
            debug_folder=tmp_path,
            **_analysis_kwargs(),
        )
    )

    assert directions.tolist() == [1]
    assert image_sizes.tolist() == [[900.0, 1200.0]]
    np.testing.assert_allclose(centers[0], SYNTHETIC_CENTER, atol=2.0)
    assert radii[0] == pytest.approx(SYNTHETIC_RADIUS, abs=5.0)
    assert sigmas[0] == pytest.approx(2.5, abs=0.5)


def test_batch_analysis_records_rejected_image(tmp_path: Path) -> None:
    _, color_image = _synthetic_image()
    good_image_path = tmp_path / "synthetic_sphere.png"
    bad_image_path = tmp_path / "synthetic_empty.png"
    assert cv2.imwrite(str(good_image_path), color_image)
    assert cv2.imwrite(
        str(bad_image_path),
        np.zeros((300, 400, 3), dtype=np.uint8),
    )

    centers, sigmas, radii, image_sizes, directions = (
        get_sphere_centers_and_blur_sigmas(
            [good_image_path, bad_image_path],
            debug_folder=tmp_path,
            **_analysis_kwargs(),
        )
    )

    assert directions.tolist() == [1, 0]
    np.testing.assert_allclose(centers[0], SYNTHETIC_CENTER, atol=2.0)
    assert np.isnan(centers[1]).all()
    assert np.isnan(radii[1])
    assert np.isnan(sigmas[1])
    assert image_sizes.tolist() == [[900.0, 1200.0], [300.0, 400.0]]
