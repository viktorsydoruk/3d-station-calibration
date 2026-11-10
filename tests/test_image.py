# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for single-image analysis and the batch wrapper."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

import station_calibration.vision.analysis as image_module
import station_calibration.vision.detection as detection_module
from station_calibration import DebugInfo
from station_calibration.vision import (
    analyze_image,
    analyze_image_array,
    analyze_image_bytes,
    decode_image,
    get_radius_outlier_mask,
    get_sphere_centers_and_blur_sigmas,
    load_image,
    split_image,
)
from station_calibration.vision.debug import debug_images_storing
from station_calibration.vision.detection import (
    estimate_direction,
    find_the_sphere_on_mask,
    fit_circle_with_covariance,
    get_bg_noise_threshold,
    get_bg_value,
    get_forground_mask,
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
    assert observation.center_covariance is not None
    assert observation.center_covariance.shape == (2, 2)
    assert np.all(np.linalg.eigvalsh(observation.center_covariance) > 0.0)


def test_fit_circle_with_covariance_matches_geometric_circle() -> None:
    rng = np.random.default_rng(42)
    angles = np.linspace(0.0, 2.0 * np.pi, 200, endpoint=False)
    x = 100.0 + 50.0 * np.cos(angles) + rng.normal(0.0, 0.1, angles.size)
    y = 200.0 + 50.0 * np.sin(angles) + rng.normal(0.0, 0.1, angles.size)

    x_c, y_c, radius, covariance = fit_circle_with_covariance(x, y)

    assert x_c == pytest.approx(100.0, abs=0.1)
    assert y_c == pytest.approx(200.0, abs=0.1)
    assert radius == pytest.approx(50.0, abs=0.1)
    assert covariance.shape == (2, 2)
    np.testing.assert_allclose(covariance, covariance.T)
    assert np.all(np.linalg.eigvalsh(covariance) > 0.0)


def _blurred_disk_image(sigma: float,
                        radius: float = 140.0,
                        center: tuple[float, float] = (500.0, 450.0),
                        ) -> np.ndarray:
    """Create a bright disk with a Gaussian-blurred edge on a noisy background."""
    height, width = 900, 1000
    rng = np.random.default_rng(11)
    image = rng.normal(8.0, 2.0, (height, width))
    cv2.circle(
        image,
        (int(center[0]), int(center[1])),
        int(radius),
        220.0,
        -1,
        lineType=cv2.LINE_AA,
    )
    return cv2.GaussianBlur(image, (0, 0), sigma)


@pytest.mark.parametrize("sigma", [1.0, 2.0, 3.0, 5.0])
def test_subpixel_edges_remove_blur_radius_bias(sigma: float) -> None:
    center = (500.0, 450.0)
    radius = 140.0
    image = _blurred_disk_image(sigma, radius=radius, center=center)
    mask = image > 30.0
    kwargs = {
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "direction": 1,
        "min_bg_pixels_on_edges": 5,
    }

    integer = find_the_sphere_on_mask(mask, **kwargs)
    subpixel = find_the_sphere_on_mask(mask, image_gray=image, **kwargs)

    assert integer is not None
    assert subpixel is not None

    # The binary contour sits at the near-background threshold, so its radius
    # grows with the edge blur. The 50 % intensity crossing is nearly unbiased.
    assert integer[2] - radius > 0.4 * sigma
    assert abs(subpixel[2] - radius) < 0.35
    assert abs(subpixel[0] - center[0]) < 0.5
    assert abs(subpixel[1] - center[1]) < 0.5


def test_subpixel_edges_follow_illumination_gradient() -> None:
    center = (500.0, 450.0)
    radius = 140.0
    image = _blurred_disk_image(3.0, radius=radius, center=center)
    gradient = np.linspace(0.65, 1.35, image.shape[1])[None, :]
    image = image * gradient
    mask = image > 30.0
    kwargs = {
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "direction": 1,
        "min_bg_pixels_on_edges": 5,
    }

    subpixel = find_the_sphere_on_mask(mask, image_gray=image, **kwargs)

    assert subpixel is not None
    # A single global edge level would pull the dark side inward. The per-ray
    # level keeps the centre and radius close to the geometric disk.
    assert abs(subpixel[0] - center[0]) < 0.7
    assert abs(subpixel[1] - center[1]) < 0.5
    assert abs(subpixel[2] - radius) < 0.5


@pytest.mark.parametrize("sigma", [10.0, 15.0, 20.0, 30.0])
def test_subpixel_edges_adapt_to_strong_blur(sigma: float) -> None:
    center = (500.0, 450.0)
    radius = 140.0
    image = _blurred_disk_image(sigma, radius=radius, center=center)
    mask = image > 30.0
    kwargs = {
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "direction": 1,
        "min_bg_pixels_on_edges": 5,
    }

    integer = find_the_sphere_on_mask(mask, **kwargs)
    subpixel = find_the_sphere_on_mask(mask, image_gray=image, **kwargs)

    assert integer is not None
    assert subpixel is not None
    binary_error = abs(integer[2] - radius)
    subpixel_error = abs(subpixel[2] - radius)
    assert integer[2] - radius > 0.4 * sigma
    assert subpixel_error < binary_error - 5.0
    assert subpixel_error < 1.0
    assert abs(subpixel[0] - center[0]) < 1.0
    assert abs(subpixel[1] - center[1]) < 1.0


def test_subpixel_edges_use_blur_aware_search(monkeypatch) -> None:
    center = (500.0, 450.0)
    radius = 140.0
    image = _blurred_disk_image(30.0, radius=radius, center=center)
    mask = image > 30.0
    kwargs = {
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "direction": 1,
        "min_bg_pixels_on_edges": 5,
    }
    searches: list[int | None] = []

    def fake_subpixel_points(
        _image: np.ndarray,
        x_c: float,
        y_c: float,
        _radius: float,
        _direction: int,
        _part: float,
        search_px: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        searches.append(search_px)
        if search_px is None or search_px < 60:
            return np.empty(0), np.empty(0)
        angles = np.linspace(0.0, 2.0 * np.pi, 32, endpoint=False)
        return (
            x_c + radius * np.cos(angles),
            y_c + radius * np.sin(angles),
        )

    monkeypatch.setattr(
        detection_module, "_subpixel_radial_points", fake_subpixel_points
    )

    result = find_the_sphere_on_mask(mask, image_gray=image, **kwargs)

    assert result is not None
    assert len(searches) == 1
    assert searches[0] is not None
    assert searches[0] >= 60
    assert result[2] == pytest.approx(radius, abs=0.01)


def test_subpixel_edges_explicit_search_disables_adaptive(monkeypatch) -> None:
    center = (500.0, 450.0)
    radius = 140.0
    image = _blurred_disk_image(30.0, radius=radius, center=center)
    mask = image > 30.0
    kwargs = {
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "direction": 1,
        "min_bg_pixels_on_edges": 5,
    }
    searches: list[int | None] = []

    def fake_subpixel_points(
        _image: np.ndarray,
        x_c: float,
        y_c: float,
        _radius: float,
        _direction: int,
        _part: float,
        search_px: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        searches.append(search_px)
        angles = np.linspace(0.0, 2.0 * np.pi, 32, endpoint=False)
        return (
            x_c + radius * np.cos(angles),
            y_c + radius * np.sin(angles),
        )

    monkeypatch.setattr(
        detection_module, "_subpixel_radial_points", fake_subpixel_points
    )

    result = find_the_sphere_on_mask(
        mask,
        image_gray=image,
        edge_search_px=17,
        **kwargs,
    )

    assert result is not None
    assert searches == [17]
    assert result[2] == pytest.approx(radius, abs=0.01)


def test_subpixel_edges_retry_with_max_search(monkeypatch) -> None:
    center = (500.0, 450.0)
    radius = 140.0
    image = _blurred_disk_image(10.0, radius=radius, center=center)
    mask = image > 30.0
    kwargs = {
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "direction": 1,
        "min_bg_pixels_on_edges": 5,
    }
    searches: list[int | None] = []

    def fake_subpixel_points(
        _image: np.ndarray,
        x_c: float,
        y_c: float,
        _radius: float,
        _direction: int,
        _part: float,
        search_px: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        searches.append(search_px)
        if search_px is None or search_px < 60:
            return np.empty(0), np.empty(0)
        angles = np.linspace(0.0, 2.0 * np.pi, 32, endpoint=False)
        return (
            x_c + radius * np.cos(angles),
            y_c + radius * np.sin(angles),
        )

    monkeypatch.setattr(
        detection_module, "_subpixel_radial_points", fake_subpixel_points
    )

    result = find_the_sphere_on_mask(mask, image_gray=image, **kwargs)

    assert result is not None
    assert len(searches) == 2
    assert searches[0] is not None and searches[1] is not None
    assert searches[1] > searches[0]
    assert result[2] == pytest.approx(radius, abs=0.01)


def test_subpixel_edges_fall_back_when_crossings_are_missing(monkeypatch) -> None:
    image = _blurred_disk_image(30.0)
    mask = image > 30.0
    kwargs = {
        "n_mov_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "direction": 1,
        "min_bg_pixels_on_edges": 5,
    }
    monkeypatch.setattr(
        detection_module,
        "_subpixel_radial_points",
        lambda *args, **kwargs: (np.empty(0), np.empty(0)),
    )

    integer = find_the_sphere_on_mask(mask, **kwargs)
    subpixel = find_the_sphere_on_mask(mask, image_gray=image, **kwargs)

    assert integer is not None
    assert subpixel is not None
    assert subpixel[2] == pytest.approx(integer[2], abs=1e-9)


def test_analyze_image_subpixel_falls_back_when_sigma_fails(monkeypatch) -> None:
    image_gray, _ = _synthetic_image()
    calls: list[float] = []

    def fake_sigma(*args, **kwargs) -> float | None:
        del kwargs
        calls.append(float(args[3]))
        if len(calls) == 1:
            return None
        return 2.5

    monkeypatch.setattr(image_module, "get_blur_sigma", fake_sigma)

    result = analyze_image(
        image_gray,
        subpixel_edges=True,
        **_analysis_kwargs(),
    )

    assert result.reason is None
    assert result.observation is not None
    assert result.observation.sigma == pytest.approx(2.5)
    assert len(calls) == 2


def test_analyze_image_subpixel_edges_improve_radius() -> None:
    image_gray, _ = _synthetic_image()

    integer = analyze_image(image_gray, **_analysis_kwargs()).observation
    subpixel = analyze_image(
        image_gray, subpixel_edges=True, **_analysis_kwargs()
    ).observation

    assert integer is not None
    assert subpixel is not None
    assert abs(integer.radius - SYNTHETIC_RADIUS) > 2.0
    assert abs(subpixel.radius - SYNTHETIC_RADIUS) < 1.0
    assert abs(subpixel.x - SYNTHETIC_CENTER[0]) < 0.5
    assert abs(subpixel.y - SYNTHETIC_CENTER[1]) < 0.5
    assert integer.binary_radius is None
    assert subpixel.binary_radius == pytest.approx(integer.radius, abs=0.1)


def test_analyze_image_bytes_extracts_synthetic_sphere() -> None:
    _, color_image = _synthetic_image()
    success, encoded = cv2.imencode(".png", color_image)
    assert success

    result = analyze_image_bytes(encoded.tobytes(), **_analysis_kwargs())

    assert result.observation is not None
    assert result.observation.x == pytest.approx(SYNTHETIC_CENTER[0], abs=2.0)
    assert result.observation.y == pytest.approx(SYNTHETIC_CENTER[1], abs=2.0)


def test_split_image_accepts_bgr_array() -> None:
    _, color_image = _synthetic_image()

    image_gray, image_color = split_image(color_image)

    assert image_gray.shape == color_image.shape[:2]
    assert image_color.shape == color_image.shape
    np.testing.assert_array_equal(image_color, color_image)


def test_split_image_interprets_2d_array_as_bayer() -> None:
    bayer = np.random.default_rng(0).integers(
        0, 255, size=(16, 24), dtype=np.uint8
    )

    image_gray, image_color = split_image(bayer)

    assert image_gray.shape == (16, 24)
    assert image_color.shape == (16, 24, 3)


def test_analyze_image_array_extracts_synthetic_sphere() -> None:
    _, color_image = _synthetic_image()

    result = analyze_image_array(color_image, **_analysis_kwargs())

    assert result.reason is None
    assert result.direction == 1
    assert result.observation is not None
    assert result.observation.x == pytest.approx(SYNTHETIC_CENTER[0], abs=2.0)
    assert result.observation.y == pytest.approx(SYNTHETIC_CENTER[1], abs=2.0)
    assert result.observation.radius == pytest.approx(SYNTHETIC_RADIUS, abs=5.0)


def _noisy_sphere_scene() -> np.ndarray:
    """Bright blurred sphere on a noisy gray background with a busy top band."""
    height, width = 600, 800
    rng = np.random.default_rng(5)
    image = np.full((height, width), 100.0)
    # A dark texture in the top band makes the direction estimator pick +1
    # without adding pixels that cross the bright-sphere threshold.
    image[:90] = rng.integers(0, 90, size=(90, width))
    cv2.circle(image, (400, 300), 100, 220.0, -1, lineType=cv2.LINE_AA)
    # Optical blur first, then sensor noise: added noise must not be smoothed
    # away, otherwise the background MAD collapses to zero.
    image = cv2.GaussianBlur(image, (0, 0), 2.0)
    image += rng.normal(0.0, 2.0, (height, width))
    return np.clip(np.rint(image), 0, 255).astype(np.uint8)


def _quantized_sphere_scene() -> np.ndarray:
    """Blurred sphere on a quantized 16/17/18/19 DN background.

    This reproduces the real 8-bit case where most background pixels equal the
    median, so the raw MAD is zero and the percentile floor is required.
    """
    height, width = 600, 800
    rng = np.random.default_rng(11)
    background = np.full((height, width), 17.0)
    pattern = rng.random((height, width))
    background[pattern < 0.17] = 16.0
    background[pattern > 0.83] = 18.0
    background[pattern > 0.995] = 19.0
    # Busy dark top band sets direction to +1 without crossing the threshold.
    background[:90] = rng.integers(0, 16, size=(90, width))
    sphere = np.zeros((height, width), dtype=np.float64)
    cv2.circle(sphere, (400, 300), 100, 100.0, -1, lineType=cv2.LINE_AA)
    sphere = cv2.GaussianBlur(sphere, (0, 0), 2.0)
    image = background + sphere
    return np.clip(np.rint(image), 0, 255).astype(np.uint8)


@pytest.mark.parametrize("method", ["mad", "percentile"])
def test_analyze_image_auto_background_methods_extract_sphere(method: str) -> None:
    image = _noisy_sphere_scene()
    kwargs = _analysis_kwargs()
    kwargs.update(
        bg_height_px=200,
        fixed_bg_threshold=0,
        bg_threshold_method=method,
        bg_color_est_perc=99.999,
        bg_noise_sigma=5.0,
    )

    result = analyze_image(image, **kwargs)

    assert result.reason is None
    assert result.direction == 1
    assert result.observation is not None
    assert result.observation.x == pytest.approx(400.0, abs=4.0)
    assert result.observation.y == pytest.approx(300.0, abs=4.0)
    assert result.observation.radius == pytest.approx(100.0, abs=6.0)
    assert result.observation.sigma == pytest.approx(2.0, abs=0.6)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"bg_threshold_method": "otsu"}, "bg_threshold_method"),
        ({"bg_noise_sigma": 0.0}, "bg_noise_sigma"),
        ({"bg_noise_sigma": float("nan")}, "bg_noise_sigma"),
    ],
)
def test_analyze_image_rejects_invalid_background_options(
    kwargs: dict,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        analyze_image(np.zeros((10, 10), dtype=np.uint8), **kwargs)


def test_get_bg_noise_threshold_is_stable_across_band_sizes() -> None:
    image = _noisy_sphere_scene()

    values = [
        get_bg_noise_threshold(image, bg_height_px=band, direction=1)
        for band in (100, 200, 300)
    ]

    assert max(values) - min(values) <= 1.0
    assert all(100.0 < value < 150.0 for value in values)


def test_analyze_image_mad_mode_floors_quantized_background() -> None:
    image = _quantized_sphere_scene()
    kwargs = _analysis_kwargs()
    kwargs.update(
        bg_height_px=200,
        fixed_bg_threshold=0,
        bg_color_est_perc=99.999,
        bg_noise_sigma=5.0,
    )

    kwargs["bg_threshold_method"] = "mad"
    mad = analyze_image(image, **kwargs)
    kwargs["bg_threshold_method"] = "percentile"
    percentile = analyze_image(image, **kwargs)

    assert mad.reason is None
    assert percentile.reason is None
    assert mad.observation is not None
    assert percentile.observation is not None
    assert mad.observation.x == pytest.approx(percentile.observation.x)
    assert mad.observation.y == pytest.approx(percentile.observation.y)
    assert mad.observation.radius == pytest.approx(percentile.observation.radius)


def _reference_get_bg_value(
    image: np.ndarray,
    bg_height_px: int,
    direction: int,
    perc: float = 99.9,
    start_from: int = 10,
) -> float:
    bg_std = [
        np.std(image[-i:] if direction == 1 else image[:i])
        for i in range(start_from, bg_height_px + 1)
    ]
    sel_arg = int(np.argmin(bg_std) + start_from)
    values = image[-sel_arg:] if direction == 1 else image[:sel_arg]
    return float(np.percentile(values, perc))


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("bg_height_px", [10, 25, 80])
def test_get_bg_value_matches_reference(
    direction: int,
    bg_height_px: int,
) -> None:
    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, size=(50, 40), dtype=np.uint8)
    start_from = 5

    expected = _reference_get_bg_value(
        image,
        bg_height_px=bg_height_px,
        direction=direction,
        start_from=start_from,
    )
    actual = get_bg_value(
        image,
        bg_height_px=bg_height_px,
        direction=direction,
        start_from=start_from,
    )

    assert actual == pytest.approx(expected, rel=1e-10, abs=1e-8)


def test_get_bg_value_handles_background_larger_than_image() -> None:
    rng = np.random.default_rng(1)
    image = rng.integers(0, 255, size=(5, 4), dtype=np.uint8)

    expected = _reference_get_bg_value(
        image,
        bg_height_px=20,
        direction=1,
        start_from=10,
    )
    actual = get_bg_value(
        image,
        bg_height_px=20,
        direction=1,
        start_from=10,
    )

    assert actual == pytest.approx(expected, rel=1e-10, abs=1e-8)


def test_get_bg_value_rejects_invalid_arguments() -> None:
    image = np.zeros((10, 10), dtype=np.uint8)

    with pytest.raises(ValueError, match="bg_height_px"):
        get_bg_value(image, bg_height_px=4, direction=1, start_from=5)
    with pytest.raises(ValueError, match="direction"):
        get_bg_value(image, bg_height_px=10, direction=0, start_from=5)


@pytest.mark.parametrize(
    "image",
    [
        np.zeros((10,), dtype=np.uint8),
        np.zeros((0, 10), dtype=np.uint8),
        np.zeros((10, 0), dtype=np.uint8),
    ],
)
def test_get_bg_value_rejects_invalid_image_shape(image: np.ndarray) -> None:
    with pytest.raises(ValueError, match="2D"):
        get_bg_value(image, bg_height_px=10)


@pytest.mark.parametrize("perc", [0.0, -1.0, 100.1, float("nan")])
def test_get_bg_value_rejects_invalid_percentile(perc: float) -> None:
    image = np.zeros((20, 20), dtype=np.uint8)

    with pytest.raises(ValueError, match="perc"):
        get_bg_value(image, bg_height_px=10, perc=perc)


def test_get_bg_value_keeps_constant_background() -> None:
    image = np.full((50, 60), 77, dtype=np.uint8)

    assert get_bg_value(image, bg_height_px=25, direction=1) == pytest.approx(77.0)
    assert get_bg_value(image, bg_height_px=25, direction=-1, perc=50) == pytest.approx(77.0)


def test_get_bg_value_stops_before_bright_object_inside_band() -> None:
    image = np.full((400, 100), 10, dtype=np.uint8)
    # A bright object starts 60 rows into the 300-row background band.  The
    # prefix search must stop before it; taking the whole band would raise the
    # percentile to the object intensity.
    image[300:340] = 200

    value = get_bg_value(image, bg_height_px=300, direction=1, perc=99.9)

    assert value == pytest.approx(10.0)


def test_get_bg_noise_threshold_uses_median_and_mad() -> None:
    image = np.empty((10, 10), dtype=np.uint8)
    image[:5] = 10
    image[5:] = 20

    # bg_height_px == start_from makes the whole band the quietest prefix:
    # median = 15, MAD = 5, sigma = 1.4826 * 5.
    expected = 15.0 + 5.0 * 1.4826 * 5.0

    assert get_bg_noise_threshold(
        image,
        bg_height_px=10,
        direction=-1,
        n_sigma=5.0,
    ) == pytest.approx(expected)

    # The percentile floor must not cap a larger MAD-based estimate.
    assert get_bg_noise_threshold(
        image,
        bg_height_px=10,
        direction=-1,
        n_sigma=5.0,
        percentile_floor=99.999,
    ) == pytest.approx(expected)


def test_get_bg_noise_threshold_zero_mad_returns_median() -> None:
    image = np.full((20, 30), 77, dtype=np.uint8)

    assert get_bg_noise_threshold(
        image,
        bg_height_px=10,
        direction=1,
    ) == pytest.approx(77.0)


def test_get_bg_noise_threshold_percentile_floor_prevents_zero_mad_collapse() -> None:
    # A quantized background: 80 % at 17 and 20 % at 19.  MAD is zero, so the
    # pure estimate would be 17 and would let the 19 DN sensor pattern into
    # the foreground mask.
    image = np.full((10, 100), 17, dtype=np.uint8)
    image[:, :20] = 19

    assert get_bg_noise_threshold(
        image,
        bg_height_px=10,
        direction=-1,
        n_sigma=5.0,
        percentile_floor=99.999,
    ) == pytest.approx(19.0)


def test_get_bg_noise_threshold_stops_before_bright_object_inside_band() -> None:
    image = np.full((400, 100), 10, dtype=np.uint8)
    image[300:340] = 200

    value = get_bg_noise_threshold(image, bg_height_px=300, direction=1)

    assert value == pytest.approx(10.0)


@pytest.mark.parametrize("n_sigma", [0.0, -1.0, float("nan"), float("inf")])
def test_get_bg_noise_threshold_rejects_invalid_n_sigma(n_sigma: float) -> None:
    image = np.zeros((20, 20), dtype=np.uint8)

    with pytest.raises(ValueError, match="n_sigma"):
        get_bg_noise_threshold(image, bg_height_px=10, n_sigma=n_sigma)


@pytest.mark.parametrize("floor", [0.0, -1.0, 100.1, float("nan")])
def test_get_bg_noise_threshold_rejects_invalid_percentile_floor(
    floor: float,
) -> None:
    image = np.zeros((20, 20), dtype=np.uint8)

    with pytest.raises(ValueError, match="percentile_floor"):
        get_bg_noise_threshold(
            image,
            bg_height_px=10,
            percentile_floor=floor,
        )


@pytest.mark.parametrize(
    ("top_noise", "bottom_noise", "expected"),
    [(120, 0, 1), (0, 120, -1), (0, 0, 0)],
)
def test_estimate_direction_detects_quiet_side(
    top_noise: int,
    bottom_noise: int,
    expected: int,
) -> None:
    rng = np.random.default_rng(0)
    image = np.zeros((200, 120), dtype=np.uint8)
    if top_noise:
        image[:100] = rng.integers(0, top_noise, size=(100, 120), dtype=np.uint8)
    if bottom_noise:
        image[100:] = rng.integers(0, bottom_noise, size=(100, 120), dtype=np.uint8)

    assert estimate_direction(image, bg_height_px=100) == expected


def test_estimate_direction_keeps_short_frame_bands_disjoint() -> None:
    rng = np.random.default_rng(1)
    image = np.zeros((40, 80), dtype=np.uint8)
    image[:20] = rng.integers(0, 120, size=(20, 80), dtype=np.uint8)

    # The requested band is longer than the frame.  Both sides must still get
    # half of the image instead of the same full-frame slice.
    assert estimate_direction(image, bg_height_px=300) == 1


def test_estimate_direction_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="2D"):
        estimate_direction(np.zeros((10,)), bg_height_px=5)
    with pytest.raises(ValueError, match="bg_height_px"):
        estimate_direction(np.zeros((10, 10), dtype=np.uint8), bg_height_px=0)


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


def test_get_forground_mask_returns_empty_mask_when_no_contour() -> None:
    mask = get_forground_mask(
        np.zeros((20, 20), dtype=np.uint8),
        bg_thr=0,
    )

    assert mask.shape == (20, 20)
    assert mask.dtype == np.bool_
    assert not np.any(mask)


def test_get_forground_mask_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="2D"):
        get_forground_mask(np.zeros((20,), dtype=np.uint8), bg_thr=0)
    with pytest.raises(ValueError, match="finite"):
        get_forground_mask(
            np.zeros((20, 20), dtype=np.uint8),
            bg_thr=float("nan"),
        )
    with pytest.raises(ValueError, match="finite"):
        get_forground_mask(
            np.zeros((20, 20), dtype=np.uint8),
            bg_thr=object(),  # type: ignore[arg-type]
        )


def test_analyze_image_reports_missing_sphere_when_mask_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_module, "estimate_direction", lambda *args, **kwargs: 1)

    image = np.zeros((300, 400), dtype=np.uint8)
    # The single pixel passes the threshold but is removed by the 3x3 opening,
    # so the foreground mask stays empty.
    image[150, 200] = 100

    result = analyze_image(
        image,
        bg_height_px=100,
        fixed_bg_threshold=30,
        print_debug=DebugInfo(False),
    )

    assert result.observation is None
    assert result.direction == 1
    assert result.reason == "sphere is not found or out of FOV"


@pytest.mark.parametrize(
    ("fill", "threshold"),
    [(10, 10), (10, 20), (100, 10)],
)
def test_analyze_image_reports_unusable_background_threshold(
    monkeypatch: pytest.MonkeyPatch,
    fill: int,
    threshold: int,
) -> None:
    monkeypatch.setattr(image_module, "estimate_direction", lambda *args, **kwargs: 1)

    result = analyze_image(
        np.full((300, 400), fill, dtype=np.uint8),
        fixed_bg_threshold=threshold,
        print_debug=DebugInfo(False),
    )

    assert result.observation is None
    assert result.reason == "background threshold is outside the usable range"


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

    image = np.zeros((300, 400), dtype=np.uint8)
    image[0, 0] = 255

    result = analyze_image(
        image,
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

    image = np.zeros((300, 400), dtype=np.uint8)
    image[0, 0] = 255

    result = analyze_image(
        image,
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


def test_batch_analysis_reports_missing_image_without_aborting(
    tmp_path: Path,
) -> None:
    _, color_image = _synthetic_image()
    good_image_path = tmp_path / "synthetic_sphere.png"
    missing_image_path = tmp_path / "missing.png"
    assert cv2.imwrite(str(good_image_path), color_image)

    centers, sigmas, radii, image_sizes, directions = (
        get_sphere_centers_and_blur_sigmas(
            [good_image_path, missing_image_path],
            debug_folder=tmp_path,
            **_analysis_kwargs(),
        )
    )

    assert directions.tolist() == [1, 0]
    np.testing.assert_allclose(centers[0], SYNTHETIC_CENTER, atol=2.0)
    assert np.isnan(centers[1]).all()
    assert np.isnan(radii[1])
    assert np.isnan(sigmas[1])
    assert image_sizes.tolist() == [[900.0, 1200.0], [0.0, 0.0]]


def test_debug_rendering_does_not_mutate_read_only_frames(tmp_path: Path) -> None:
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    image.setflags(write=False)
    before = image.copy()
    target = tmp_path / "debug.png"

    debug_images_storing(
        target,
        image,
        x_c_pos=15.0,
        y_c_pos=10.0,
        radius=5.0,
    )

    assert target.is_file()
    np.testing.assert_array_equal(image, before)


def test_split_image_converts_bgra_and_rejects_invalid_input() -> None:
    image = np.zeros((4, 5, 4), dtype=np.uint8)

    image_gray, image_color = split_image(image)

    assert image_gray.shape == (4, 5)
    assert image_color.shape == (4, 5, 3)
    with pytest.raises(ValueError, match="could not be loaded"):
        split_image(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported image shape"):
        split_image(np.zeros((4,), dtype=np.uint8))


def test_load_image_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Could not read image file"):
        load_image(tmp_path / "missing.png")


def test_decode_image_rejects_empty_and_invalid_bytes() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        decode_image(b"")
    with pytest.raises(ValueError, match="Could not decode image bytes"):
        decode_image(b"not an image")


def test_radius_outlier_mask_can_use_a_method_independent_reference() -> None:
    radii = np.array([150.0] * 10 + [170.0])
    sigmas = np.ones_like(radii)
    reference_radii = np.full_like(radii, 159.0)

    assert bool(get_radius_outlier_mask(radii, sigmas)[-1])
    assert not bool(get_radius_outlier_mask(radii, sigmas, reference_radii).any())


def test_radius_outlier_mask_rejects_mismatched_reference_shape() -> None:
    radii = np.array([150.0, 151.0])
    sigmas = np.ones_like(radii)

    with pytest.raises(ValueError, match="same shape"):
        get_radius_outlier_mask(radii, sigmas, np.array([150.0]))


def test_storage_radius_filter_can_use_a_reference() -> None:
    centers = np.zeros((11, 2))

    radii = np.array([150.0] * 10 + [170.0])
    sigmas = np.ones_like(radii)
    image_module.filtering_data_by_radius(
        [],
        centers,
        sigmas,
        radii,
    )
    assert np.isnan(radii[-1])

    radii = np.array([150.0] * 10 + [170.0])
    sigmas = np.ones_like(radii)
    image_module.filtering_data_by_radius(
        [],
        centers,
        sigmas,
        radii,
        reference_radii=np.full_like(radii, 159.0),
    )
    assert np.isfinite(radii).all()
    assert np.isfinite(sigmas).all()
