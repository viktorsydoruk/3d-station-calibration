"""Tests for the configurable stop/readiness policy."""

from __future__ import annotations

import pytest

from station_calibration import StopPolicy, StopReason


def test_default_policy_targets_500_valid_observations() -> None:
    policy = StopPolicy()

    assert policy.target_observations == 500
    assert policy.max_observations is None

    status = policy.evaluate(499, min_observations=14)
    assert status.ready is False
    assert status.reason is StopReason.NOT_READY
    assert status.detail is None

    status = policy.evaluate(500, min_observations=14)
    assert status.ready is True
    assert status.reason is StopReason.TARGET_OBSERVATIONS
    assert status.detail is not None
    assert "500" in status.detail


def test_policy_waits_for_minimum_observations() -> None:
    policy = StopPolicy(target_observations=14)

    assert policy.evaluate(13, min_observations=14).ready is False

    status = policy.evaluate(14, min_observations=14)
    assert status.ready is True
    assert status.reason is StopReason.TARGET_OBSERVATIONS


def test_max_observations_stops_before_target() -> None:
    policy = StopPolicy(target_observations=500, max_observations=100)

    assert policy.evaluate(99, min_observations=14).ready is False

    status = policy.evaluate(100, min_observations=14)
    assert status.ready is True
    assert status.reason is StopReason.MAX_OBSERVATIONS
    assert status.detail is not None
    assert "100" in status.detail


def test_explicit_stop_overrides_counters_after_minimum() -> None:
    policy = StopPolicy(target_observations=500)

    status = policy.evaluate(
        20,
        min_observations=14,
        explicit_detail="operator finished",
    )

    assert status.ready is True
    assert status.reason is StopReason.EXPLICIT
    assert status.detail == "operator finished"


def test_explicit_stop_before_minimum_is_not_ready() -> None:
    policy = StopPolicy(target_observations=500)

    status = policy.evaluate(
        13,
        min_observations=14,
        explicit_detail="too early",
    )

    assert status.ready is False
    assert status.reason is StopReason.NOT_READY
    assert status.detail is not None
    assert "minimum" in status.detail


def test_policy_without_limits_is_never_ready_automatically() -> None:
    policy = StopPolicy(target_observations=None, max_observations=None)

    status = policy.evaluate(500, min_observations=14)

    assert status.ready is False
    assert status.reason is StopReason.NOT_READY


def test_invalid_stop_limits_raise() -> None:
    with pytest.raises(ValueError, match="target_observations"):
        StopPolicy(target_observations=0)

    with pytest.raises(ValueError, match="max_observations"):
        StopPolicy(max_observations=0)
