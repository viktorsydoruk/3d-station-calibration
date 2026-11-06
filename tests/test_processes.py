# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the calibration fitting loop and its stability fixes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml
from scipy.optimize import OptimizeResult

import station_calibration.processes as processes
from station_calibration import (
    CalibrationObservation,
    DebugInfo,
    Settings,
    get_calibration_data,
    load_all_points,
    store_calibration,
)


DATA_FILE = Path(__file__).parent / "data" / "CalibrationAllPoints.dat"


def _make_data(n_points: int = 20) -> tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray, tuple[int, int]
]:
    robot_positions = np.column_stack(
        [
            np.linspace(0.0, 100.0, n_points),
            np.linspace(0.0, 50.0, n_points),
            np.linspace(10.0, 90.0, n_points),
        ]
    )
    center_points = np.column_stack(
        [
            np.linspace(1000.0, 1400.0, n_points),
            np.linspace(700.0, 1100.0, n_points),
        ]
    )
    radii = np.full(n_points, 12.0)
    sigmas = np.full(n_points, 1.5)
    return robot_positions, center_points, radii, sigmas, (2448, 2048)


@pytest.fixture
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the numerical pipeline with deterministic fakes."""
    state = SimpleNamespace(
        fit_calls=[],
        adjust_calls=0,
        check_results=[],
    )

    base_intrinsic = np.array(
        [
            [2000.0, 0.0, 1224.0],
            [0.0, 2000.0, 1024.0],
            [0.0, 0.0, 1.0],
        ]
    )
    base_extrinsic = np.eye(4)
    base_extrinsic[2, 3] = 80.0

    def fake_calibrate(robot_positions, image_center_points, radii, sigmas, **kwargs):
        state.fit_calls.append(
            {
                "n_distortion_coefs": kwargs["n_distortion_coefs"],
                "loss_f_scale": kwargs["loss_f_scale"],
                "center_points": np.array(image_center_points, copy=True),
            }
        )
        return OptimizeResult(
            x=np.zeros(2),
            fun=np.zeros(2 * len(robot_positions)),
            success=True,
            cost=0.0,
            message="fake",
        )

    def fake_get_calibration(params, **kwargs):
        distortion = np.zeros(14)
        if kwargs["n_distortion_coefs"]:
            distortion[0] = -1e-7
        return (
            base_intrinsic.copy(),
            distortion,
            np.zeros(3),
            base_extrinsic.copy(),
        )

    def fake_adjust_center_points(image_center_points, radii, intrinsic_matrix):
        state.adjust_calls += 1
        return np.array(image_center_points, copy=True) + np.array([5.0, -3.0])

    def fake_check_distortion(distortion, intrinsic_matrix, image_size_xy):
        if state.check_results:
            return state.check_results.pop(0)
        return True

    monkeypatch.setattr(processes, "calibrate_camera", fake_calibrate)
    monkeypatch.setattr(processes, "get_calibration", fake_get_calibration)
    monkeypatch.setattr(
        processes, "find_robot_home_pos_shift", lambda *args, **kwargs: np.zeros(3)
    )
    monkeypatch.setattr(
        processes, "adjust_image_center_points", fake_adjust_center_points
    )
    monkeypatch.setattr(
        processes, "check_distortion_monotonicity", fake_check_distortion
    )
    monkeypatch.setattr(
        processes, "calculate_RMSE", lambda result, standardized=True: 0.0
    )

    return state


def _settings(tmp_path: Path, **overrides) -> Settings:
    options = {
        "debug": False,
        "n_iterations": 1,
        "allowed_outliers": 0,
        "n_distortion_coefs": 4,
        "focal_length_initial": 2000.0,
        "camera_distance_initial": 80.0,
    }
    options.update(overrides)
    return Settings(tmp_path, **options)


def test_pipeline_forwards_loss_f_scale(
    tmp_path: Path,
    fake_pipeline: SimpleNamespace,
) -> None:
    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()

    get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        _settings(tmp_path, loss_f_scale=2.5),
        DebugInfo(False),
    )

    assert fake_pipeline.fit_calls
    assert all(
        call["loss_f_scale"] == 2.5
        for call in fake_pipeline.fit_calls
    )


def test_final_refit_uses_adjusted_center_points(
    tmp_path: Path,
    fake_pipeline: SimpleNamespace,
) -> None:
    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()

    result = get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        _settings(tmp_path),
        DebugInfo(False),
    )

    assert fake_pipeline.adjust_calls == 1
    assert len(fake_pipeline.fit_calls) == 2
    np.testing.assert_allclose(
        fake_pipeline.fit_calls[0]["center_points"], center_points
    )
    np.testing.assert_allclose(
        fake_pipeline.fit_calls[1]["center_points"],
        center_points + np.array([5.0, -3.0]),
    )
    np.testing.assert_allclose(
        result[1], center_points + np.array([5.0, -3.0])
    )


def test_small_allowed_outlier_fraction_still_runs_a_fit(
    tmp_path: Path,
    fake_pipeline: SimpleNamespace,
) -> None:
    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()

    result = get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        _settings(tmp_path, allowed_outliers=0.001),
        DebugInfo(False),
    )

    assert result[5] is not None
    assert len(fake_pipeline.fit_calls) == 2


def _install_scripted_outlier_fit(
    monkeypatch: pytest.MonkeyPatch,
    rmse_values: list[float],
) -> None:
    values = iter(rmse_values)

    def fake_calibrate(robot_positions, image_center_points, radii, sigmas, **kwargs):
        n_points = len(robot_positions)
        residuals = np.zeros(2 * n_points)
        if n_points == 20:
            # One clearly flagged point in the initial fit.
            residuals[2] = 100.0
        return OptimizeResult(
            x=np.zeros(2),
            fun=residuals,
            success=True,
            cost=0.0,
            message="fake",
        )

    monkeypatch.setattr(processes, "calibrate_camera", fake_calibrate)
    monkeypatch.setattr(
        processes,
        "calculate_RMSE",
        lambda result, standardized=True: next(values),
    )


def test_outlier_removal_returns_best_fit_and_matching_mask(
    tmp_path: Path,
    fake_pipeline: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scripted_outlier_fit(monkeypatch, [5.0, 4.0])
    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()

    result = get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        _settings(tmp_path, allowed_outliers=1),
        DebugInfo(False),
    )

    assert result[6] == pytest.approx(4.0)
    assert result[7].sum() == len(robot_positions) - 1
    assert not result[7][1]


def test_outlier_removal_keeps_initial_fit_when_refit_is_worse(
    tmp_path: Path,
    fake_pipeline: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scripted_outlier_fit(monkeypatch, [4.0, 5.0])
    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()

    result = get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        _settings(tmp_path, allowed_outliers=1),
        DebugInfo(False),
    )

    assert result[6] == pytest.approx(4.0)
    assert result[7].all()


def test_nonmonotonic_distortion_refits_without_distortion(
    tmp_path: Path,
    fake_pipeline: SimpleNamespace,
) -> None:
    fake_pipeline.check_results = [False]
    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()

    result = get_calibration_data(
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_size_xy,
        _settings(tmp_path),
        DebugInfo(False),
    )

    assert [call["n_distortion_coefs"] for call in fake_pipeline.fit_calls] == [
        4,
        0,
        0,
    ]
    assert result[8] == 0
    np.testing.assert_allclose(result[4], np.zeros(14))


def test_negative_allowed_outliers_raises(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.allowed_outliers = -1.0
    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()

    with pytest.raises(ValueError, match="allowed_outliers"):
        get_calibration_data(
            robot_positions,
            center_points,
            radii,
            sigmas,
            image_size_xy,
            settings,
            DebugInfo(False),
        )


def test_too_few_measurements_raise(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with pytest.raises(ValueError, match="At least 14"):
        get_calibration_data(
            np.zeros((13, 3)),
            np.zeros((13, 2)),
            np.ones(13),
            np.ones(13),
            (2448, 2048),
            settings,
            DebugInfo(False),
        )


def test_store_calibration_writes_nozzle_home_position(tmp_path: Path) -> None:
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    nozzle_home_position = np.array([1.0, 2.0, 3.0])

    store_calibration(
        nozzle_home_position=nozzle_home_position,
        intrinsic_matrix=np.eye(3),
        extrinsic_matrix=np.eye(4),
        distortion_coefficients=np.zeros(14),
        intrinsic_std=np.zeros((3, 3)),
        rot_vec_std=np.zeros(3),
        tra_vec_std=np.zeros(3),
        distortion_std=np.zeros(14),
        image_xy=(2448, 2048),
        output_folder=output_folder,
        n_distortion_coefs=4,
        rmse=0.25,
        observation_count=10,
        observations_used=9,
        sphere_home_position=np.array([4.0, 5.0, 6.0]),
    )

    calibration = yaml.safe_load(
        (output_folder / "calibration_data.yaml").read_text(encoding="utf-8")
    )
    assert calibration["schema_version"] == 1
    assert calibration["nozzle"]["home_position"] == nozzle_home_position.tolist()
    camera = calibration["camera"]
    assert camera["resolution"] == [2448, 2048]
    assert camera["n_distortion_coefs"] == 4
    assert camera["rmse"] == pytest.approx(0.25)
    assert camera["observation_count"] == 10
    assert camera["observations_used"] == 9
    assert camera["sphere_home_position"] == [4.0, 5.0, 6.0]
    assert set(camera["errors"]) == {
        "intrinsic_std",
        "rot_vec_std",
        "tra_vec_std",
        "distortion_std",
    }


def test_main_stores_nozzle_end_home_position(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import station_calibration.cli as app_module

    robot_positions, center_points, radii, sigmas, image_size_xy = _make_data()
    directions = np.ones(len(robot_positions))
    observations = tuple(
        CalibrationObservation(
            robot_position=robot_positions[index],
            image_center=center_points[index],
            radius=float(radii[index]),
            sigma=float(sigmas[index]),
            direction=int(directions[index]),
            image_shape=(image_size_xy[1], image_size_xy[0]),
            source=f"image-{index}",
        )
        for index in range(len(robot_positions))
    )
    pos_home = np.array([1.0, 2.0, 3.0])
    nozzle_home_position = np.array([10.0, 20.0, 30.0])
    optimize_result = OptimizeResult(x=np.zeros(8), fun=np.zeros(4))
    calibration_result = SimpleNamespace(
        pos_home=pos_home,
        center_points_adjusted=center_points,
        intrinsic_matrix=np.eye(3),
        extrinsic_matrix=np.eye(4),
        distortion=np.zeros(14),
        optimize_result=optimize_result,
        rmse=0.0,
        fit_mask=np.array(
            [True] * (len(robot_positions) - 1) + [False],
            dtype=bool,
        ),
        n_distortion_coefs=0,
        image_size_xy=image_size_xy,
        observation_count=len(robot_positions),
        n_used=len(robot_positions),
    )
    captured = {}

    class FakeSource:
        def __init__(self, settings, print_debug):
            self.settings = settings
            self.print_debug = print_debug

        def load(self):
            return SimpleNamespace(
                observations=observations,
                rejections=(),
                apply_radius_filter=False,
            )

    class FakeSession:
        def __init__(self, settings, print_debug, *, fit_every_n=None,
                     apply_radius_filter=True):
            self.fit_observations = observations
            self.added_observations = 0
            captured["session"] = self
            captured["fit_every_n"] = fit_every_n
            captured["apply_radius_filter"] = apply_radius_filter

        def add_rejection(self, rejection):
            pass

        def add_observation(self, observation):
            self.added_observations += 1
            if self.added_observations == 20:
                captured["partial_fits"] = 1
                return calibration_result
            return None

        def finish(self):
            return calibration_result

    def fake_get_nozzle_end_home_position(**kwargs):
        captured["nozzle_kwargs"] = kwargs
        return nozzle_home_position, 24.0, {}

    def fake_calculate_errors(result):
        return np.zeros(len(result.x))

    def fake_calculate_calibration_errors(*args, **kwargs):
        return np.zeros((3, 3)), np.zeros(14), np.zeros(3), np.zeros(3)

    def fake_store_calibration(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(app_module, "FolderCalibrationSource", FakeSource)
    monkeypatch.setattr(app_module, "CalibrationSession", FakeSession)
    monkeypatch.setattr(app_module, "calculate_errors", fake_calculate_errors)
    monkeypatch.setattr(
        app_module, "get_nozzle_end_home_position", fake_get_nozzle_end_home_position
    )
    monkeypatch.setattr(
        app_module,
        "calculate_calibration_errors",
        fake_calculate_calibration_errors,
    )
    monkeypatch.setattr(app_module, "store_calibration", fake_store_calibration)

    app_module.main(tmp_path, debug=False, fit_every_n=5)

    assert captured["session"].added_observations == len(observations)
    assert captured["fit_every_n"] == 5
    assert captured["apply_radius_filter"] is False
    assert captured["partial_fits"] == 1
    np.testing.assert_allclose(
        captured["nozzle_home_position"], nozzle_home_position
    )

    nozzle_kwargs = captured["nozzle_kwargs"]
    assert len(nozzle_kwargs["radii"]) == len(observations) - 1
    assert len(nozzle_kwargs["sigmas"]) == len(observations) - 1
    assert nozzle_kwargs["robot_positions"].shape == (len(observations) - 1, 3)
    assert nozzle_kwargs["image_center_points"].shape == (len(observations) - 1, 2)
    np.testing.assert_allclose(
        nozzle_kwargs["image_center_points"],
        center_points[:-1],
    )


def test_main_reraises_pipeline_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import station_calibration.cli as app_module

    class FailSource:
        def __init__(self, settings, print_debug):
            pass

        def load(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(app_module, "FolderCalibrationSource", FailSource)

    with pytest.raises(RuntimeError, match="boom"):
        app_module.main(tmp_path, debug=False)

    assert "RuntimeError: boom" in capsys.readouterr().err


def test_stored_point_cloud_regression(tmp_path: Path) -> None:
    robot_positions, center_points, radii, sigmas, image_sizes, directions = (
        load_all_points(DATA_FILE)
    )
    valid = np.logical_and(~np.isnan(sigmas), ~np.isnan(radii))
    image_size_xy = np.flip(np.nanmax(image_sizes, axis=0)).astype(int).tolist()

    result = get_calibration_data(
        robot_positions[valid],
        center_points[valid],
        radii[valid],
        sigmas[valid],
        image_size_xy,
        _settings(tmp_path, n_iterations=3),
        DebugInfo(False),
    )

    pos_home, _, intrinsic, extrinsic, distortion, optimize_result, rmse, mask, n_dist = result
    assert int(mask.sum()) == 492
    assert n_dist == 4
    assert optimize_result.success
    assert len(optimize_result.x) == 12

    np.testing.assert_allclose(
        pos_home,
        np.array([315.4901712371497, -111.52137043930243, -35.08113896105615]),
        rtol=1e-6,
        atol=1e-3,
    )
    np.testing.assert_allclose(
        [intrinsic[0, 0], intrinsic[1, 1]],
        [22000.968301554833, 21723.396608092873],
        rtol=1e-6,
    )
    assert intrinsic[0, 2] == 1224.0
    assert intrinsic[1, 2] == 1024.0
    np.testing.assert_allclose(
        extrinsic[:3, 3],
        [-1.243445171204292e-04, 4.525225150326526e-04, 7.353737262475748e01],
        rtol=1e-5,
        atol=1e-8,
    )
    # The rational coefficients are highly correlated, so different BLAS/LAPACK
    # implementations move the least-squares optimum slightly. Keep this check
    # strong enough to catch a model change but tolerant of platform round-off.
    assert np.all(np.isfinite(distortion[:4]))
    np.testing.assert_allclose(
        distortion[:4],
        [
            -5.785585378343614e-01,
            -2.536041213352001e02,
            -2.685658088476287e-02,
            6.293788374856212e-03,
        ],
        rtol=5e-3,
        atol=1e-6,
    )
    np.testing.assert_allclose(distortion[4:], np.zeros(10))
    assert rmse == pytest.approx(4.366936342185351, rel=1e-6)
