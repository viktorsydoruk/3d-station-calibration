# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

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
    ReadinessPolicy,
    ReadinessTolerances,
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
        "target_observations": 100,
    }
    options.update(overrides)
    return Settings(tmp_path, **options)


def _fast_readiness(**overrides) -> ReadinessPolicy:
    options = {
        "enabled": True,
        "checkpoint_interval": 1,
        "stable_checkpoints": 1,
        "min_inlier_fraction": 0.9,
        "tolerances": ReadinessTolerances(),
    }
    options.update(overrides)
    return ReadinessPolicy(**options)


def _observation(
    index: int,
    *,
    radius: float = 12.0,
    sigma: float = 1.5,
    direction: int = 1,
    image_shape: tuple[int, int] = (2048, 2448),
    center_covariance: np.ndarray | None = None,
    binary_radius: float | None = None,
) -> CalibrationObservation:
    return CalibrationObservation(
        robot_position=np.array([float(index), float(index % 7), 20.0 + float(index)]),
        image_center=np.array([1000.0 + float(index), 900.0 + float(index % 5)]),
        radius=radius,
        sigma=sigma,
        direction=direction,
        image_shape=image_shape,
        source=f"image-{index}",
        center_covariance=center_covariance,
        binary_radius=binary_radius,
    )


@pytest.fixture
def fake_fit(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the numerical fit with a deterministic fake."""
    state = SimpleNamespace(
        calls=[],
        mask=None,
        fail=None,
        success=True,
        intrinsic=np.eye(3, dtype=np.float64),
        extrinsic=np.eye(4, dtype=np.float64),
        distortion=np.zeros(14, dtype=np.float64),
        pos_home=None,
        rmse=0.0,
    )

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
                "center_covariances": center_covariances,
            }
        )
        pos_home = (
            np.mean(robot_positions, axis=0)
            if state.pos_home is None
            else np.asarray(state.pos_home, dtype=np.float64)
        )
        return (
            pos_home,
            np.array(center_points, copy=True),
            np.array(state.intrinsic, copy=True),
            np.array(state.extrinsic, copy=True),
            np.array(state.distortion, copy=True),
            OptimizeResult(
                x=np.zeros(8),
                fun=np.zeros(2 * n_points),
                success=state.success,
                cost=0.0,
                message="fake",
            ),
            state.rmse,
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


def test_session_defers_auto_fit_until_radius_filter_has_enough(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path))

    for index in range(13):
        assert session.add_observation(_observation(index)) is None

    assert session.can_fit is False

    # The 14th observation is a radius outlier, leaving only 13 for the fit.
    assert session.add_observation(_observation(13, radius=1000.0)) is None
    assert session.n_observations == 14
    assert session.can_fit is True
    assert session.can_auto_fit is False
    assert session.fit_count == 0
    assert session.last_fit_error is None

    # A further valid observation leaves the required 14 after filtering.
    result = session.add_observation(_observation(14))

    assert result is not None
    assert session.fit_count == 1
    assert len(fake_fit.calls[-1]["radii"]) == 14


def test_session_finish_reports_too_few_after_radius_filter(
    tmp_path: Path,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(13):
        session.add_observation(_observation(index))
    session.add_observation(_observation(13, radius=1000.0))

    with pytest.raises(ValueError, match="after radius filtering, got 13"):
        session.finish()

    assert session.last_fit_error is not None
    assert "after radius filtering" in session.last_fit_error


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


def test_session_first_auto_fit_ignores_large_fit_every_n(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=20)

    for index in range(14):
        session.add_observation(_observation(index))

    assert session.fit_count == 1
    assert session.last_result is not None
    assert session.last_result.observation_count == 14

    for index in range(14, 33):
        assert session.add_observation(_observation(index)) is None
    assert session.fit_count == 1

    result = session.add_observation(_observation(33))

    assert result is not None
    assert session.fit_count == 2
    assert result.observation_count == 34


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


def test_session_radius_filter_uses_binary_reference(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        session.add_observation(
            _observation(index, radius=12.0, binary_radius=12.0)
        )
    # The sub-pixel radius is high relative to the sub-pixel mean, but the
    # binary-mask radius for the same frame is consistent with all the others.
    session.add_observation(
        _observation(14, radius=30.0, binary_radius=12.0)
    )

    result = session.finish()

    assert len(fake_fit.calls[-1]["radii"]) == 15
    assert result.fit_observation_indices.tolist() == list(range(15))
    assert result.used_mask.tolist() == [True] * 15


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


def test_observation_accepts_zero_sigma_but_not_negative() -> None:
    observation = _observation(0, sigma=0.0)

    assert observation.sigma == 0.0

    with pytest.raises(ValueError, match="sigma"):
        _observation(0, sigma=-0.1)


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


def test_session_rejects_non_converged_fit_and_keeps_previous_result(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        session.add_observation(_observation(index))

    first_result = session.finish()
    session.add_observation(_observation(14))

    fake_fit.success = False
    with pytest.raises(ValueError, match="did not converge"):
        session.finish()

    assert session.last_result is first_result
    assert session.fit_count == 1
    assert session.last_fit_error is not None
    assert "did not converge" in session.last_fit_error

    fake_fit.success = True
    final_result = session.finish()

    assert final_result is not first_result
    assert session.fit_count == 2
    assert session.last_fit_error is None


def test_session_rejects_non_finite_fit_output(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        session.add_observation(_observation(index))

    fake_fit.intrinsic = np.array(
        [
            [np.nan, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )

    with pytest.raises(ValueError, match="non-finite intrinsic_matrix"):
        session.finish()

    assert session.last_result is None
    assert session.fit_count == 0
    assert session.last_fit_error is not None


def test_session_rejects_fit_that_drops_all_observations(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.mask = np.zeros(14, dtype=bool)
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    for index in range(14):
        session.add_observation(_observation(index))

    with pytest.raises(ValueError, match="rejected all observations"):
        session.finish()

    assert session.last_result is None
    assert session.fit_count == 0


def test_session_default_stop_policy_uses_settings(tmp_path: Path) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    assert session.stop_policy.target_observations == 100
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


def test_session_passes_complete_center_covariances_to_fit(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)
    covariance = np.array([[0.01, 0.002], [0.002, 0.02]])

    for index in range(14):
        session.add_observation(
            _observation(index, center_covariance=covariance)
        )
    session.finish()

    passed = fake_fit.calls[-1]["center_covariances"]
    assert passed is not None
    np.testing.assert_allclose(passed, np.tile(covariance, (14, 1, 1)))


def test_calibration_observation_rejects_invalid_center_covariance() -> None:
    with pytest.raises(ValueError, match="shape"):
        CalibrationObservation(
            robot_position=np.zeros(3),
            image_center=np.zeros(2),
            radius=12.0,
            sigma=1.5,
            direction=1,
            image_shape=(2048, 2448),
            center_covariance=np.zeros((2, 3)),
        )


def test_session_falls_back_when_center_covariances_are_partial(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)
    covariance = np.eye(2) * 0.01

    for index in range(14):
        session.add_observation(
            _observation(
                index,
                center_covariance=covariance if index < 13 else None,
            )
        )
    session.finish()

    assert fake_fit.calls[-1]["center_covariances"] is None


def _ready_session(
    tmp_path: Path,
    *,
    target: int = 15,
    **readiness_overrides,
) -> CalibrationSession:
    return CalibrationSession(
        _settings(tmp_path),
        fit_every_n=1,
        stop_policy=StopPolicy(target_observations=target),
        readiness_policy=_fast_readiness(**readiness_overrides),
    )


def test_session_becomes_ready_when_fit_parameters_saturate(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    fake_fit.intrinsic = np.diag([1000.0, 1000.0, 1.0])
    fake_fit.extrinsic = np.eye(4)
    session = _ready_session(tmp_path)

    for index in range(14):
        session.add_observation(_observation(index))

    assert session.fit_count == 1
    assert session.is_ready is False
    assert session.readiness_reason is StopReason.NOT_READY

    session.add_observation(_observation(14))

    assert session.fit_count == 2
    assert session.is_ready is True
    assert session.readiness_reason is StopReason.SATURATED
    assert len(session.fit_history) == 2


def test_session_readiness_waits_for_enough_checkpoints(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=1,
        stop_policy=StopPolicy(target_observations=15),
        readiness_policy=_fast_readiness(checkpoint_interval=10),
    )

    for index in range(15):
        session.add_observation(_observation(index))

    assert session.fit_count == 2
    assert len(session.fit_history) == 1
    assert session.is_ready is False
    assert session.readiness_reason is StopReason.WAITING_FOR_CHECKPOINTS


def test_session_stale_fit_blocks_readiness(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = _ready_session(tmp_path)

    for index in range(15):
        session.add_observation(_observation(index))
    assert session.is_ready is True

    session.add_observation(_observation(15), fit=False)

    assert session.is_ready is False
    assert session.readiness_reason is StopReason.STALE_FIT


def test_session_failed_fit_blocks_readiness(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = _ready_session(tmp_path)

    for index in range(15):
        session.add_observation(_observation(index))
    assert session.is_ready is True

    fake_fit.fail = RuntimeError("fit failed")
    with pytest.raises(RuntimeError, match="fit failed"):
        session.fit()

    assert session.is_ready is False
    assert session.readiness_reason is StopReason.FIT_FAILED


def test_session_too_few_inliers_blocks_readiness(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = _ready_session(tmp_path)

    for index in range(14):
        session.add_observation(_observation(index))

    fake_fit.mask = np.array([True] * 5 + [False] * 10)
    session.add_observation(_observation(14))

    assert session.is_ready is False
    assert session.readiness_reason is StopReason.INSUFFICIENT_INLIERS


def test_session_mixed_directions_block_readiness(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = _ready_session(tmp_path)

    for index in range(14):
        session.add_observation(_observation(index))
    session.add_observation(_observation(14, direction=-1))

    assert session.is_ready is False
    assert session.readiness_reason is StopReason.MIXED_DIRECTIONS


def test_session_explicit_stop_forces_readiness(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=1,
        stop_policy=StopPolicy(target_observations=100),
        readiness_policy=_fast_readiness(),
    )

    for index in range(14):
        session.add_observation(_observation(index))

    session.request_stop("operator finished")

    assert session.is_ready is True
    assert session.readiness_reason is StopReason.EXPLICIT
    assert session.readiness_status.forced is True


def test_session_max_observations_forces_readiness(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=1,
        stop_policy=StopPolicy(target_observations=100, max_observations=14),
        readiness_policy=_fast_readiness(),
    )

    for index in range(14):
        session.add_observation(_observation(index))

    assert session.is_ready is True
    assert session.readiness_reason is StopReason.MAX_OBSERVATIONS
    assert session.readiness_status.forced is True


def test_session_disables_saturation_without_incremental_fits(
    tmp_path: Path,
) -> None:
    session = CalibrationSession(_settings(tmp_path), fit_every_n=None)

    assert session.readiness_policy.enabled is False


def test_session_finish_if_ready_waits_for_saturation(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = CalibrationSession(
        _settings(tmp_path),
        fit_every_n=1,
        stop_policy=StopPolicy(target_observations=15),
        readiness_policy=_fast_readiness(checkpoint_interval=10),
    )

    for index in range(15):
        session.add_observation(_observation(index))

    assert session.count_status.ready is True
    assert session.finish_if_ready() is None
    assert session.is_ready is False


def test_session_finish_if_ready_returns_saturated_result(
    tmp_path: Path,
    fake_fit: SimpleNamespace,
) -> None:
    fake_fit.pos_home = np.zeros(3)
    session = _ready_session(tmp_path)

    for index in range(15):
        session.add_observation(_observation(index))

    result = session.finish_if_ready()

    assert result is session.last_result
    assert session.is_ready is True
