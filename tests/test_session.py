"""Tests for the stateful calibration session."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

import station_calibration.session as session_module
from station_calibration import (
    CalibrationObservation,
    CalibrationSession,
    ImageAnalysisResult,
    Settings,
    SphereObservation,
    StopPolicy,
    StopReason,
)


def _settings(tmp_path: Path, **overrides) -> Settings:
    options = {
        "debug": False,
        "n_iterations": 1,
        "allowed_outliers": 0,
        "n_distortion_coefs": 4,
        "focal_length_initial": 2000.0,
        "camera_distance_initial": 80.0,
        "target_observations": 500,
    }
    options.update(overrides)
    return Settings(tmp_path, **options)


def _observation(
    index: int,
    *,
    radius: float = 12.0,
    sigma: float = 1.5,
    direction: int = 1,
    image_shape: tuple[int, int] = (2048, 2448),
) -> CalibrationObservation:
    return CalibrationObservation(
        robot_position=np.array([float(index), float(index % 7), 20.0 + float(index)]),
        image_center=np.array([1000.0 + float(index), 900.0 + float(index % 5)]),
        radius=radius,
        sigma=sigma,
        direction=direction,
        image_shape=image_shape,
        source=f"image-{index}",
    )


@pytest.fixture
def fake_fit(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the numerical fit with a deterministic fake."""
    state = SimpleNamespace(
        calls=[],
        mask=None,
        fail=None,
    )

    def fake_get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        settings,
        print_debug,
    ):
        if state.fail is not None:
            raise state.fail

        n_points = len(robot_positions)
        mask = (
            np.asarray(state.mask, dtype=bool)
            if state.mask is not None
            else np.ones(n_points, dtype=bool)
        )
        state.calls.append(
            {
                "robot_positions": np.array(robot_positions, copy=True),
                "center_points": np.array(center_points, copy=True),
                "radii": np.array(radii, copy=True),
                "sigmas": np.array(sigmas, copy=True),
                "image_size_xy": image_size_xy,
                "settings": settings,
            }
        )
        return (
            np.mean(robot_positions, axis=0),
            np.array(center_points, copy=True),
            np.eye(3),
            np.eye(4),
            np.zeros(14),
            OptimizeResult(
                x=np.zeros(8),
                fun=np.zeros(2 * n_points),
                success=True,
                cost=0.0,
                message="fake",
            ),
            0.0,
            mask,
            int(settings.n_distortion_coefs),
        )

    monkeypatch.setattr(session_module, "get_calibration_data", fake_get_calibration_data)
    return state


def test_session_waits_for_minimum_then_fits(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path))

    for index in range(13):
        assert session.add_observation(_observation(index)) is None

    assert session.n_observations == 13
    assert not session.can_fit
    assert session.fit_count == 0
    assert session.last_result is None

    result = session.add_observation(_observation(13))

    assert result is not None
    assert result is session.last_result
    assert session.fit_count == 1
    assert result.observation_count == 14
    assert result.n_used == 14
    assert result.used_mask.tolist() == [True] * 14
    assert result.fit_observation_indices.tolist() == list(range(14))
    assert result.fit_mask.tolist() == [True] * 14
    assert result.image_size_xy == (2448, 2048)
    assert len(result.center_points_adjusted) == 14
    assert len(fake_fit.calls) == 1
    assert len(fake_fit.calls[0]["radii"]) == 14


def test_session_fit_every_n_and_final_fit(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=3)

    for index in range(14):
        session.add_observation(_observation(index))

    assert session.fit_count == 1
    assert session.add_observation(_observation(14)) is None
    assert session.add_observation(_observation(15)) is None
    assert session.fit_count == 1

    result = session.add_observation(_observation(16))

    assert result is not None
    assert session.fit_count == 2
    assert result.observation_count == 17
    assert len(fake_fit.calls[-1]["radii"]) == 17


def test_session_finish_forces_final_fit(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        assert session.add_observation(_observation(index)) is None

    assert session.fit_count == 0

    first_result = session.finish()

    assert session.fit_count == 1
    assert first_result.observation_count == 14
    assert session.finish() is first_result

    assert session.add_observation(_observation(14)) is None
    assert session.fit_count == 1

    final_result = session.finish()

    assert final_result is not first_result
    assert session.fit_count == 2
    assert final_result.observation_count == 15
    assert len(fake_fit.calls[-1]["radii"]) == 15
    assert session.finish() is final_result


def test_session_applies_radius_filter_without_dropping_data(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        session.add_observation(_observation(index))
    session.add_observation(_observation(14, radius=1000.0))

    result = session.finish()

    assert len(fake_fit.calls[-1]["radii"]) == 14
    assert result.fit_observation_indices.tolist() == list(range(14))
    assert result.used_mask.tolist() == [True] * 14 + [False]
    assert session.n_observations == 15
    assert session.observations[-1].radius == 1000.0
    assert len(session.fit_observations) == 14
    assert len(session.used_observations) == 14


def test_session_can_skip_radius_filter(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=None,
        apply_radius_filter=False,
    )

    for index in range(14):
        session.add_observation(_observation(index))
    session.add_observation(_observation(14, radius=1000.0))

    result = session.finish()

    assert len(fake_fit.calls[-1]["radii"]) == 15
    assert result.used_mask.tolist() == [True] * 15


def test_session_maps_calibration_outlier_mask(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.mask = np.array([False] + [True] * 15)
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(16):
        session.add_observation(_observation(index))

    result = session.finish()

    assert result.fit_observation_indices.tolist() == list(range(16))
    assert result.fit_mask.tolist() == [False] + [True] * 15
    assert result.used_mask.tolist() == [False] + [True] * 15
    assert result.n_used == 15
    assert len(result.center_points_adjusted) == 16
    assert len(session.fit_observations) == 16
    assert len(session.used_observations) == 15


def test_session_add_analysis_tracks_rejections(tmp_path: Path) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)
    rejection = ImageAnalysisResult(
        observation=None,
        direction=0,
        image_shape=(2048, 2448),
        reason="direction is undefined",
    )

    assert session.add_analysis(rejection, np.zeros(3), source="bad") is None

    assert session.n_observations == 0
    assert session.n_rejections == 1
    assert session.rejections[0].reason == "direction is undefined"
    assert session.rejections[0].source == "bad"
    assert session.image_size_xy == (2448, 2048)

    analysis = ImageAnalysisResult(
        observation=SphereObservation(1000.0, 900.0, 12.0, 1.5),
        direction=1,
        image_shape=(2048, 2448),
    )

    assert session.add_analysis(
        analysis,
        np.array([1.0, 2.0, 3.0]),
        source="good",
    ) is None

    assert session.n_observations == 1
    observation = session.observations[0]
    assert observation.image_center.tolist() == [1000.0, 900.0]
    assert observation.robot_position.tolist() == [1.0, 2.0, 3.0]
    assert observation.source == "good"


def test_session_rejects_invalid_fit_policy(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with pytest.raises(ValueError, match="min_observations"):
        CalibrationSession(settings, min_observations=13)
    with pytest.raises(ValueError, match="fit_every_n"):
        CalibrationSession(settings, fit_every_n=0)


def test_session_fit_requires_minimum_observations(tmp_path: Path) -> None:
    session = CalibrationSession(_settings(tmp_path))

    with pytest.raises(ValueError, match="At least 14"):
        session.fit()
    with pytest.raises(ValueError, match="No valid observations"):
        session.finish()


def test_observation_requires_valid_direction() -> None:
    with pytest.raises(ValueError, match="direction"):
        _observation(0, direction=0)


def test_session_records_fit_failure_and_can_retry(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        session.add_observation(_observation(index))

    fake_fit.fail = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        session.finish()

    assert session.last_fit_error is not None
    assert "boom" in session.last_fit_error
    assert session.n_observations == 14

    fake_fit.fail = None
    result = session.finish()

    assert result.observation_count == 14
    assert session.fit_count == 1
    assert session.last_fit_error is None


def test_session_default_stop_policy_uses_settings(tmp_path: Path) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    assert session.stop_policy.target_observations == 500
    assert session.stop_policy.max_observations is None
    assert session.stop_reason is StopReason.NOT_READY
    assert session.is_ready is False
    assert session.finish_if_ready() is None


def test_session_stop_counts_only_valid_observations(tmp_path: Path) -> None:
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=None,
        stop_policy=StopPolicy(target_observations=14),
    )

    for index in range(13):
        session.add_observation(_observation(index))

    rejection = ImageAnalysisResult(
        observation=None,
        direction=0,
        image_shape=(2048, 2448),
        reason="sphere is not found or out of FOV",
    )
    session.add_analysis(rejection, np.zeros(3), source="rejected")

    assert session.n_observations == 13
    assert session.n_rejections == 1
    assert session.is_ready is False

    session.add_observation(_observation(13))

    assert session.is_ready is True
    assert session.stop_reason is StopReason.TARGET_OBSERVATIONS
    assert session.stop_detail is not None
    assert "14" in session.stop_detail


def test_session_stop_max_observations(tmp_path: Path) -> None:
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=None,
        stop_policy=StopPolicy(target_observations=500, max_observations=14),
    )

    for index in range(13):
        session.add_observation(_observation(index))
    assert session.is_ready is False

    session.add_observation(_observation(13))

    assert session.is_ready is True
    assert session.stop_reason is StopReason.MAX_OBSERVATIONS
    assert session.stop_detail is not None
    assert "14" in session.stop_detail


def test_session_explicit_stop(tmp_path: Path) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        session.add_observation(_observation(index))

    assert session.is_ready is False
    assert session.stop_requested is False

    session.request_stop("operator finished")

    assert session.stop_requested is True
    assert session.is_ready is True
    assert session.stop_reason is StopReason.EXPLICIT
    assert session.stop_detail == "operator finished"


def test_session_finish_if_ready(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=None,
        stop_policy=StopPolicy(target_observations=14),
    )

    for index in range(13):
        session.add_observation(_observation(index))

    assert session.finish_if_ready() is None

    session.add_observation(_observation(13))

    result = session.finish_if_ready()

    assert result is not None
    assert result.observation_count == 14
    assert session.fit_count == 1
    assert session.finish_if_ready() is result


def test_session_rejects_stop_target_below_minimum(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="target_observations"):
        CalibrationSession(
            _settings(tmp_path),
            stop_policy=StopPolicy(target_observations=13),
        )

    with pytest.raises(ValueError, match="max_observations"):
        CalibrationSession(
            _settings(tmp_path),
            stop_policy=StopPolicy(target_observations=500, max_observations=13),
        )
