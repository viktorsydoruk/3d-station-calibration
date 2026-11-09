# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the saturation-based readiness policy."""

from __future__ import annotations

from math import cos, radians, sin
from types import SimpleNamespace

import numpy as np
import pytest

from station_calibration import (
    FitSnapshot,
    ReadinessPolicy,
    ReadinessTolerances,
    StopReason,
    StopStatus,
)


def _rotation_z(angle_deg: float) -> np.ndarray:
    angle = radians(angle_deg)
    return np.array(
        [
            [cos(angle), -sin(angle), 0.0],
            [sin(angle), cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _result(
    n_observations: int = 100,
    *,
    n_used: int | None = None,
    fx: float = 1000.0,
    fy: float = 1000.0,
    cx: float = 500.0,
    cy: float = 400.0,
    distortion: np.ndarray | None = None,
    n_distortion_coefs: int = 0,
    rotation: np.ndarray | None = None,
    translation: np.ndarray | None = None,
    pos_home: np.ndarray | None = None,
    rmse: float = 1.0,
) -> SimpleNamespace:
    intrinsic = np.array(
        [
            [fx, 0.0, cx],
            [0.0, fy, cy],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    extrinsic = np.eye(4, dtype=np.float64)
    if rotation is not None:
        extrinsic[:3, :3] = rotation
    if translation is not None:
        extrinsic[:3, 3] = translation
    return SimpleNamespace(
        observation_count=int(n_observations),
        n_used=int(n_observations if n_used is None else n_used),
        intrinsic_matrix=intrinsic,
        extrinsic_matrix=extrinsic,
        distortion=(
            np.zeros(14, dtype=np.float64)
            if distortion is None
            else np.asarray(distortion, dtype=np.float64)
        ),
        n_distortion_coefs=int(n_distortion_coefs),
        pos_home=(
            np.zeros(3, dtype=np.float64)
            if pos_home is None
            else np.asarray(pos_home, dtype=np.float64)
        ),
        rmse=float(rmse),
    )


def _snapshot(n_observations: int = 100, **kwargs) -> FitSnapshot:
    return FitSnapshot.from_result(_result(n_observations, **kwargs))


def _stop_ready() -> StopStatus:
    return StopStatus(
        ready=True,
        reason=StopReason.TARGET_OBSERVATIONS,
        detail="reached target",
    )


def _policy(**kwargs) -> ReadinessPolicy:
    options = {
        "enabled": True,
        "checkpoint_interval": 10,
        "stable_checkpoints": 3,
        "min_inlier_fraction": 0.9,
    }
    options.update(kwargs)
    return ReadinessPolicy(**options)


def _evaluate(
    policy: ReadinessPolicy,
    snapshots: list[FitSnapshot],
    *,
    result: SimpleNamespace | None = None,
    stop_status: StopStatus | None = None,
    last_fit_error: str | None = None,
    new_since_fit: int = 0,
    n_observations: int | None = None,
    used_directions: list[int] | None = None,
):
    if result is None:
        if snapshots:
            result = _result(snapshots[-1].n_observations)
        else:
            result = _result(100)
    if n_observations is None:
        n_observations = int(getattr(result, "observation_count", 100))
    return policy.evaluate(
        stop_status or _stop_ready(),
        last_result=result,
        last_fit_error=last_fit_error,
        new_since_fit=new_since_fit,
        n_observations=n_observations,
        snapshots=snapshots,
        used_directions=used_directions,
    )


def test_snapshot_extracts_fit_quantities_without_nozzle() -> None:
    snapshot = _snapshot(
        120,
        n_used=115,
        fx=1200.0,
        fy=1210.0,
        cx=610.0,
        cy=420.0,
        translation=np.array([1.0, 2.0, 3.0]),
        pos_home=np.array([4.0, 5.0, 6.0]),
        n_distortion_coefs=4,
        distortion=np.array([0.1, 0.2, 0.3, 0.4] + [0.0] * 10),
    )

    assert snapshot.n_observations == 120
    assert snapshot.n_used == 115
    assert snapshot.fx == 1200.0
    assert snapshot.fy == 1210.0
    assert snapshot.cx == 610.0
    assert snapshot.cy == 420.0
    assert snapshot.distortion.tolist() == [0.1, 0.2, 0.3, 0.4]
    assert snapshot.translation.tolist() == [1.0, 2.0, 3.0]
    assert snapshot.pos_home.tolist() == [4.0, 5.0, 6.0]
    assert snapshot.n_distortion_coefs == 4


def test_count_floor_is_still_required() -> None:
    policy = _policy()
    status = policy.evaluate(
        StopStatus(False, StopReason.NOT_READY),
        last_result=_result(100),
        last_fit_error=None,
        new_since_fit=0,
        n_observations=100,
        snapshots=[],
    )

    assert status.ready is False
    assert status.reason is StopReason.NOT_READY


def test_disabled_policy_uses_count_only() -> None:
    status = _evaluate(
        _policy(enabled=False),
        [],
        result=_result(100),
    )

    assert status.ready is True
    assert status.reason is StopReason.TARGET_OBSERVATIONS


def test_requires_a_successful_current_fit() -> None:
    policy = _policy()

    status = policy.evaluate(
        _stop_ready(),
        last_result=None,
        last_fit_error=None,
        new_since_fit=0,
        n_observations=100,
        snapshots=[],
    )
    assert status.ready is False
    assert status.reason is StopReason.STALE_FIT

    status = _evaluate(
        policy,
        [_snapshot(100)],
        last_fit_error="RuntimeError: boom",
    )
    assert status.ready is False
    assert status.reason is StopReason.FIT_FAILED

    status = _evaluate(
        policy,
        [_snapshot(100)],
        result=_result(100),
        new_since_fit=1,
        n_observations=101,
    )
    assert status.ready is False
    assert status.reason is StopReason.STALE_FIT


def test_requires_enough_inliers() -> None:
    status = _evaluate(
        _policy(),
        [_snapshot(100, n_used=89)],
        result=_result(100, n_used=89),
    )

    assert status.ready is False
    assert status.reason is StopReason.INSUFFICIENT_INLIERS
    assert "90" in (status.detail or "")


def test_rejects_mixed_nozzle_directions() -> None:
    status = _evaluate(
        _policy(),
        [_snapshot(100)],
        used_directions=[1, -1],
    )

    assert status.ready is False
    assert status.reason is StopReason.MIXED_DIRECTIONS


def test_waits_for_enough_checkpoints() -> None:
    status = _evaluate(
        _policy(),
        [_snapshot(90), _snapshot(100)],
        result=_result(100),
    )

    assert status.ready is False
    assert status.reason is StopReason.WAITING_FOR_CHECKPOINTS
    assert "6" in (status.detail or "")


def test_waits_when_no_checkpoints_exist() -> None:
    status = _evaluate(
        _policy(),
        [],
        result=_result(100),
    )

    assert status.ready is False
    assert status.reason is StopReason.WAITING_FOR_CHECKPOINTS
    assert "no fit checkpoints" in (status.detail or "")


def test_stable_windows_are_saturated() -> None:
    snapshots = [_snapshot(n) for n in (50, 60, 70, 80, 90, 100)]
    status = _evaluate(
        _policy(),
        snapshots,
        result=_result(100),
    )

    assert status.ready is True
    assert status.reason is StopReason.SATURATED
    assert status.saturation_ratio == pytest.approx(0.0)


def test_translation_change_prevents_saturation() -> None:
    previous = [
        _snapshot(n, translation=np.array([0.0, 0.0, 100.0]))
        for n in (50, 60, 70)
    ]
    recent = [
        _snapshot(n, translation=np.array([0.0, 0.0, 100.1]))
        for n in (80, 90, 100)
    ]
    status = _evaluate(
        _policy(),
        previous + recent,
        result=_result(100, translation=np.array([0.0, 0.0, 100.1])),
    )

    assert status.ready is False
    assert status.reason is StopReason.NOT_SATURATED
    assert status.failed_parameter == "translation"
    assert status.saturation_ratio == pytest.approx(2.0)


def test_each_parameter_can_block_saturation() -> None:
    cases = [
        (
            "fx",
            {"fx": 1000.0},
            {"fx": 1002.0},
        ),
        (
            "cx",
            {"cx": 500.0},
            {"cx": 500.1},
        ),
        (
            "rotation",
            {"rotation": _rotation_z(0.0)},
            {"rotation": _rotation_z(0.02)},
        ),
        (
            "pos_home",
            {"pos_home": np.zeros(3)},
            {"pos_home": np.array([0.1, 0.0, 0.0])},
        ),
        (
            "distortion",
            {
                "n_distortion_coefs": 1,
                "distortion": np.array([0.0] + [0.0] * 13),
            },
            {
                "n_distortion_coefs": 1,
                "distortion": np.array([0.0002] + [0.0] * 13),
            },
        ),
    ]

    for name, old_kwargs, new_kwargs in cases:
        previous = [_snapshot(n, **old_kwargs) for n in (50, 60, 70)]
        recent = [_snapshot(n, **new_kwargs) for n in (80, 90, 100)]
        status = _evaluate(
            _policy(),
            previous + recent,
            result=_result(100, **new_kwargs),
        )

        assert status.ready is False, name
        assert status.reason is StopReason.NOT_SATURATED, name
        assert status.failed_parameter == name, name


def test_checkpoints_with_different_distortion_models_are_not_mixed() -> None:
    snapshots = [
        _snapshot(50, n_distortion_coefs=4, distortion=np.zeros(14)),
        _snapshot(60, n_distortion_coefs=4, distortion=np.zeros(14)),
        _snapshot(70, n_distortion_coefs=4, distortion=np.zeros(14)),
        _snapshot(80, n_distortion_coefs=0),
        _snapshot(90, n_distortion_coefs=0),
        _snapshot(100, n_distortion_coefs=0),
    ]
    status = _evaluate(
        _policy(),
        snapshots,
        result=_result(100, n_distortion_coefs=0),
    )

    assert status.ready is False
    assert status.reason is StopReason.WAITING_FOR_CHECKPOINTS


def test_only_the_contiguous_latest_model_checkpoints_are_used() -> None:
    snapshots = [
        _snapshot(30, n_distortion_coefs=0),
        _snapshot(40, n_distortion_coefs=0),
        _snapshot(50, n_distortion_coefs=0),
        _snapshot(60, n_distortion_coefs=4, distortion=np.zeros(14)),
        _snapshot(70, n_distortion_coefs=4, distortion=np.zeros(14)),
        _snapshot(80, n_distortion_coefs=4, distortion=np.zeros(14)),
        _snapshot(90, n_distortion_coefs=0),
        _snapshot(100, n_distortion_coefs=0),
        _snapshot(110, n_distortion_coefs=0),
    ]
    status = _evaluate(
        _policy(),
        snapshots,
        result=_result(110, n_distortion_coefs=0),
    )

    assert status.ready is False
    assert status.reason is StopReason.WAITING_FOR_CHECKPOINTS
    assert "3 of 6" in (status.detail or "")


def test_explicit_and_maximum_stops_are_forced() -> None:
    policy = _policy()

    for reason in (StopReason.EXPLICIT, StopReason.MAX_OBSERVATIONS):
        status = policy.evaluate(
            StopStatus(True, reason, "forced"),
            last_result=None,
            last_fit_error=None,
            new_since_fit=0,
            n_observations=100,
            snapshots=[],
        )
        assert status.ready is True
        assert status.reason is reason
        assert status.forced is True


def test_invalid_readiness_settings_raise() -> None:
    with pytest.raises(ValueError, match="checkpoint_interval"):
        ReadinessPolicy(checkpoint_interval=0)
    with pytest.raises(ValueError, match="stable_checkpoints"):
        ReadinessPolicy(stable_checkpoints=0)
    with pytest.raises(ValueError, match="min_inlier_fraction"):
        ReadinessPolicy(min_inlier_fraction=0.0)
    with pytest.raises(ValueError, match="focal_relative"):
        ReadinessTolerances(focal_relative=0.0)
