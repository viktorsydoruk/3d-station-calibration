# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the nozzle-home bootstrap diagnostic."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from station_calibration import CalibrationObservation, Settings
from station_calibration import uncertainty
from station_calibration.uncertainty import (
    _ensure_symmetric_psd,
    _estimate_global_center_covariance,
    _nozzle_axis,
    _radius_sigma_predictions,
    _statistics,
    bootstrap_nozzle_home,
)


def _synthetic_case(
    tmp_path,
    *,
    center_covariance: bool = True,
    fit_mask: np.ndarray | None = None,
) -> tuple[list[CalibrationObservation], SimpleNamespace, Settings, dict[str, Any]]:
    n_points = 30
    z_positions = np.linspace(40.0, 100.0, n_points)
    robot_positions = np.column_stack(
        [
            np.linspace(-10.0, 10.0, n_points),
            np.linspace(-8.0, 8.0, n_points),
            z_positions,
        ]
    )
    pos_home = np.array([0.0, 0.0, 20.0])
    intrinsic_matrix = np.array(
        [
            [2000.0, 0.0, 1000.0],
            [0.0, 2000.0, 800.0],
            [0.0, 0.0, 1.0],
        ]
    )
    extrinsic_matrix = np.eye(4)

    relative_positions = robot_positions - pos_home
    center_points = np.column_stack(
        [
            intrinsic_matrix[0, 0] * relative_positions[:, 0] / relative_positions[:, 2]
            + intrinsic_matrix[0, 2],
            intrinsic_matrix[1, 1] * relative_positions[:, 1] / relative_positions[:, 2]
            + intrinsic_matrix[1, 2],
        ]
    )
    radii = intrinsic_matrix[0, 0] * 5.0 / relative_positions[:, 2]
    sigmas = 0.8 + 0.2 * np.sin(z_positions)

    observation_covariance = np.eye(2) * 0.25 if center_covariance else None
    observations = [
        CalibrationObservation(
            robot_position=robot_positions[index],
            image_center=center_points[index],
            radius=float(radii[index]),
            sigma=float(sigmas[index]),
            direction=1,
            image_shape=(1600, 2000),
            center_covariance=observation_covariance,
        )
        for index in range(n_points)
    ]

    if fit_mask is None:
        fit_mask = np.ones(n_points, dtype=bool)
    result = SimpleNamespace(
        pos_home=pos_home,
        center_points_adjusted=center_points + 0.05,
        intrinsic_matrix=intrinsic_matrix,
        extrinsic_matrix=extrinsic_matrix,
        distortion=np.zeros(14),
        optimize_result=SimpleNamespace(
            raw_fun=np.zeros(2 * n_points),
        ),
        rmse=0.5,
        fit_mask=fit_mask,
        image_size_xy=(2000, 1600),
        n_distortion_coefs=0,
    )
    settings = Settings(
        tmp_path,
        debug=False,
        n_iterations=1,
        allowed_outliers=0,
        n_distortion_coefs=0,
        center_weighting=True,
    )
    base = {
        "pos_home": pos_home,
        "intrinsic_matrix": intrinsic_matrix,
        "extrinsic_matrix": extrinsic_matrix,
        "center_points": center_points,
        "radii": radii,
        "sigmas": sigmas,
    }
    return observations, result, settings, base


class FakeFit:
    """Fast deterministic stand-in for the iterative calibration pipeline."""

    def __init__(self, base: dict[str, Any], *, fail_every: int | None = None) -> None:
        self.base = base
        self.fail_every = fail_every
        self.calls: list[dict[str, Any]] = []
        self.attempts = 0

    def __call__(
        self,
        robot_positions: np.ndarray,
        center_points: np.ndarray,
        radii: np.ndarray,
        sigmas: np.ndarray,
        image_size_xy: tuple[int, int],
        settings: Settings,
        print_debug: Any,
        *,
        center_covariances: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, Any, float, np.ndarray, int]:
        del robot_positions, image_size_xy, print_debug
        call_index = self.attempts
        self.attempts += 1
        if self.fail_every is not None and call_index % self.fail_every == 0:
            raise ValueError("synthetic fit failure")
        self.calls.append(
            {
                "settings": settings,
                "center_covariances": center_covariances,
                "center_points": np.array(center_points, copy=True),
                "radii": np.array(radii, copy=True),
                "sigmas": np.array(sigmas, copy=True),
            }
        )

        center_shift = center_points.mean(axis=0) - self.base["center_points"].mean(axis=0)
        radius_shift = radii.mean() - self.base["radii"].mean()
        sigma_shift = sigmas.mean() - self.base["sigmas"].mean()
        pos_home = (
            self.base["pos_home"]
            + np.array([0.001, -0.001, 0.002]) * center_shift[0]
            + np.array([0.0, 0.001, -0.001]) * center_shift[1]
            + np.array([0.0, 0.0, 0.003]) * radius_shift
        )
        intrinsic_matrix = self.base["intrinsic_matrix"].copy()
        intrinsic_matrix[0, 0] += 0.01 * sigma_shift
        extrinsic_matrix = self.base["extrinsic_matrix"].copy()
        adjusted_centers = center_points + 0.05
        n_points = len(center_points)
        optimize_result = SimpleNamespace(
            fun=np.zeros(2 * n_points),
            jac=np.zeros((2 * n_points, 10)),
            raw_fun=np.zeros(2 * n_points),
        )
        return (
            pos_home,
            adjusted_centers,
            intrinsic_matrix,
            extrinsic_matrix,
            np.zeros(14),
            optimize_result,
            0.5,
            np.ones(n_points, dtype=bool),
            0,
        )


def test_bootstrap_nozzle_home_returns_finite_statistics(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations, result, settings, base = _synthetic_case(tmp_path)
    fake_fit = FakeFit(base)
    monkeypatch.setattr(uncertainty, "get_calibration_data", fake_fit)

    bootstrap = bootstrap_nozzle_home(
        observations,
        result,
        settings,
        n_bootstrap=24,
        seed=11,
    )

    assert bootstrap.n_requested == 24
    assert bootstrap.n_success == 24
    assert bootstrap.n_failed == 0
    assert bootstrap.samples.shape == (24, 3)
    assert bootstrap.covariance.shape == (3, 3)
    assert np.allclose(bootstrap.covariance, bootstrap.covariance.T)
    assert np.all(np.isfinite(bootstrap.samples))
    assert np.all(bootstrap.std >= 0.0)
    assert bootstrap.norm_std >= 0.0
    assert bootstrap.along_std >= 0.0
    assert bootstrap.perpendicular_std >= 0.0
    assert np.isclose(np.linalg.norm(bootstrap.axis), 1.0)
    assert np.all(bootstrap.lower_1sigma <= bootstrap.upper_1sigma)
    assert np.all(bootstrap.lower_2sigma <= bootstrap.lower_1sigma)
    assert np.all(bootstrap.upper_1sigma <= bootstrap.upper_2sigma)
    assert np.allclose(bootstrap.bias, bootstrap.mean - bootstrap.original)
    assert len(fake_fit.calls) == 24
    assert all(call["settings"].allowed_outliers == 0 for call in fake_fit.calls)
    assert all(call["center_covariances"] is not None for call in fake_fit.calls)

    payload = json.dumps(bootstrap.as_dict())
    assert "covariance" in payload


def test_bootstrap_nozzle_home_falls_back_without_center_covariances(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations, result, settings, base = _synthetic_case(
        tmp_path,
        center_covariance=False,
    )
    fake_fit = FakeFit(base)
    monkeypatch.setattr(uncertainty, "get_calibration_data", fake_fit)

    bootstrap = bootstrap_nozzle_home(
        observations,
        result,
        settings,
        n_bootstrap=8,
        seed=3,
    )

    assert bootstrap.n_success == 8
    assert all(call["center_covariances"] is None for call in fake_fit.calls)


def test_bootstrap_nozzle_home_counts_failed_replicates(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations, result, settings, base = _synthetic_case(tmp_path)
    fake_fit = FakeFit(base, fail_every=2)
    monkeypatch.setattr(uncertainty, "get_calibration_data", fake_fit)

    bootstrap = bootstrap_nozzle_home(
        observations,
        result,
        settings,
        n_bootstrap=10,
        seed=5,
    )

    assert bootstrap.n_success == 5
    assert bootstrap.n_failed == 5
    assert len(bootstrap.failure_messages) == 5


def test_bootstrap_nozzle_home_raises_when_every_replicate_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations, result, settings, base = _synthetic_case(tmp_path)
    fake_fit = FakeFit(base, fail_every=1)
    monkeypatch.setattr(uncertainty, "get_calibration_data", fake_fit)

    with pytest.raises(RuntimeError, match="all nozzle bootstrap replicates failed"):
        bootstrap_nozzle_home(
            observations,
            result,
            settings,
            n_bootstrap=3,
            seed=7,
        )


def test_bootstrap_nozzle_home_validates_arguments(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations, result, settings, base = _synthetic_case(tmp_path)
    fake_fit = FakeFit(base)
    monkeypatch.setattr(uncertainty, "get_calibration_data", fake_fit)

    with pytest.raises(ValueError, match="at least 1"):
        bootstrap_nozzle_home(observations, result, settings, n_bootstrap=0)

    result.fit_mask = np.zeros(len(observations), dtype=bool)
    with pytest.raises(ValueError, match="no inlier observations"):
        bootstrap_nozzle_home(observations, result, settings, n_bootstrap=1)

    result.fit_mask = np.zeros(len(observations) + 1, dtype=bool)
    with pytest.raises(ValueError, match="one entry per fit observation"):
        bootstrap_nozzle_home(observations, result, settings, n_bootstrap=1)


def test_center_covariance_validation_rejects_bad_matrices() -> None:
    with pytest.raises(ValueError, match="finite 2x2"):
        _ensure_symmetric_psd(np.eye(3))

    with pytest.raises(ValueError, match="positive semidefinite"):
        _ensure_symmetric_psd(np.array([[1.0, 2.0], [2.0, 1.0]]))


def test_global_center_covariance_falls_back_to_rmse() -> None:
    result = SimpleNamespace(
        optimize_result=SimpleNamespace(raw_fun=None),
        rmse=0.0,
    )
    assert np.allclose(_estimate_global_center_covariance(result), np.eye(2))

    result.rmse = 2.0
    assert np.allclose(_estimate_global_center_covariance(result), 4.0 * np.eye(2))

    result.optimize_result.raw_fun = np.array([1.0, 2.0, 3.0])
    result.rmse = 1.5
    assert np.allclose(_estimate_global_center_covariance(result), 2.25 * np.eye(2))


def test_radius_sigma_predictions_fall_back_and_reject_bad_coefficients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n_points = 12
    robot_positions = np.column_stack(
        [
            np.linspace(-5.0, 5.0, n_points),
            np.linspace(-4.0, 4.0, n_points),
            np.linspace(30.0, 90.0, n_points),
        ]
    )
    radii = np.full(n_points, 100.0)
    sigmas = np.full(n_points, 1.0)
    result = SimpleNamespace(
        extrinsic_matrix=np.eye(4),
        pos_home=np.zeros(3),
    )
    debug_info = {
        "sphere_radius_estimation": {
            "coef_for_radii": np.full(n_points, 0.02),
            "n_sigma_est": 0.5,
        }
    }

    real_polyfit = np.polyfit
    degrees: list[int] = []

    def fake_polyfit(z, values, deg, **kwargs):
        degrees.append(deg)
        if deg == 4:
            raise ValueError("forced rank deficiency")
        return real_polyfit(z, values, deg=1, **kwargs)

    monkeypatch.setattr(uncertainty.np, "polyfit", fake_polyfit)
    predictions = _radius_sigma_predictions(
        robot_positions,
        radii,
        sigmas,
        result,
        10.0,
        debug_info,
    )
    assert degrees == [4, 1]
    assert all(np.all(np.isfinite(array)) for array in predictions)

    bad_debug = {
        "sphere_radius_estimation": {
            "coef_for_radii": np.zeros(n_points),
            "n_sigma_est": 0.5,
        }
    }
    with pytest.raises(ValueError, match="usable radius scaling"):
        _radius_sigma_predictions(
            robot_positions,
            radii,
            sigmas,
            result,
            10.0,
            bad_debug,
        )


def test_nozzle_axis_and_statistics_handle_degenerate_inputs() -> None:
    result = SimpleNamespace(extrinsic_matrix=np.eye(4))
    assert np.allclose(_nozzle_axis(0.0, result), np.array([0.0, 1.0, 0.0]))

    statistics = _statistics(
        np.array([[1.0, 2.0, 3.0]]),
        np.array([1.0, 2.0, 3.0]),
        np.zeros(3),
    )
    assert np.allclose(statistics[2], np.zeros((3, 3)))
    assert statistics[4] == 0.0


def test_bootstrap_summary_rounds_to_two_std_digits() -> None:
    result = uncertainty.NozzleBootstrapResult(
        original=np.array([315.487391203948, -111.520987654321, -35.572123456789]),
        samples=np.zeros((1, 3)),
        mean=np.array([315.4881, -111.4987, -35.5732]),
        bias=np.array([0.0005, 0.0228, -0.0008]),
        covariance=np.eye(3),
        std=np.array([0.0024, 0.0613, 0.0055]),
        norm_std=0.0617,
        axis=np.array([0.0, 1.0, 0.0]),
        along_std=0.0613,
        perpendicular_std=0.0037,
        lower_1sigma=np.array([315.485, -111.582, -35.578]),
        upper_1sigma=np.array([315.490, -111.437, -35.567]),
        lower_2sigma=np.array([315.483, -111.643, -35.583]),
        upper_2sigma=np.array([315.492, -111.376, -35.562]),
        n_requested=8,
        n_success=8,
        n_failed=0,
        failure_messages=(),
    )

    payload = result.as_dict()

    assert payload["original"] == pytest.approx([315.4874, -111.521, -35.5721])
    assert payload["mean"] == pytest.approx([315.4881, -111.499, -35.5732])
    assert payload["bias"] == pytest.approx([0.0005, 0.023, -0.0008])
    assert payload["std"] == pytest.approx([0.0024, 0.061, 0.0055])
    assert payload["norm_std"] == pytest.approx(0.062)
    assert payload["along_std"] == pytest.approx(0.061)
    assert payload["perpendicular_std"] == pytest.approx(0.0037)
    # Replicate distribution data keeps full precision.
    assert payload["samples"] == [[0.0, 0.0, 0.0]]
    assert payload["covariance"] == np.eye(3).tolist()
