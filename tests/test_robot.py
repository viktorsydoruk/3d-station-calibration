# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for robot-home and nozzle geometry."""

from __future__ import annotations

import numpy as np
import pytest

from station_calibration import (
    find_robot_home_pos_shift,
    get_nozzle_end_home_position,
)


def test_home_shift_accepts_zero_sigmas() -> None:
    """The sigma offset keeps zero-sigma weights finite."""
    rng = np.random.default_rng(1)
    n_points = 20
    robot_positions = np.column_stack(
        [
            rng.uniform(-50.0, 50.0, n_points),
            rng.uniform(-50.0, 50.0, n_points),
            rng.uniform(-20.0, 20.0, n_points),
        ]
    )
    image_center_points = np.column_stack(
        [
            rng.uniform(800.0, 1600.0, n_points),
            rng.uniform(600.0, 1400.0, n_points),
        ]
    )
    intrinsic_matrix = np.array(
        [
            [2000.0, 0.0, 1224.0],
            [0.0, 2000.0, 1024.0],
            [0.0, 0.0, 1.0],
        ]
    )

    shift = find_robot_home_pos_shift(
        robot_positions,
        image_center_points,
        intrinsic_matrix,
        np.eye(4),
        np.zeros(5),
        np.zeros(n_points),
    )

    assert np.all(np.isfinite(shift))


def test_nozzle_end_home_position_returns_geometry_and_debug_data() -> None:
    n_points = 24
    z_positions = np.linspace(0.0, 80.0, n_points)
    robot_positions = np.column_stack(
        [
            np.linspace(-40.0, 40.0, n_points),
            np.linspace(-20.0, 20.0, n_points),
            z_positions,
        ]
    )
    image_center_points = np.column_stack(
        [
            1200.0 + 0.2 * robot_positions[:, 0],
            1000.0 + 0.3 * robot_positions[:, 1],
        ]
    )
    intrinsic_matrix = np.array(
        [
            [2000.0, 0.0, 1224.0],
            [0.0, 2000.0, 1024.0],
            [0.0, 0.0, 1.0],
        ]
    )
    sphere_home_position = np.array([10.0, 20.0, 30.0])

    nozzle, sphere_diameter, debug_info = get_nozzle_end_home_position(
        sphere_home_position=sphere_home_position,
        robot_positions=robot_positions,
        image_center_points=image_center_points,
        intrinsic_matrix=intrinsic_matrix,
        extrinsic_matrix=np.eye(4),
        distortion=np.zeros(5),
        sigmas=np.ones(n_points),
        radii=np.full(n_points, 100.0),
        all_directions=np.ones(n_points),
    )

    assert nozzle.shape == (3,)
    assert np.all(np.isfinite(nozzle))
    assert sphere_diameter > 0.0
    assert set(debug_info) == {
        "scaling_visualization",
        "n_sigma_estimation",
        "sphere_radius_estimation",
        "sphere_radius_vs_depth",
    }
    scaling = debug_info["scaling_visualization"]
    assert scaling["z_pos"].shape == scaling["scale"].shape
    assert scaling["z_pos"].size > 3
    assert debug_info["n_sigma_estimation"]["confidence"] is None


def test_nozzle_end_home_position_bootstrap_confidence_interval() -> None:
    inputs = _nozzle_inputs()
    n_points = len(inputs["sigmas"])
    inputs["sigmas"] = np.linspace(1.0, 5.0, n_points)

    _, _, base_debug = get_nozzle_end_home_position(**inputs)
    coef = np.asarray(
        base_debug["sphere_radius_estimation"]["coef_for_radii"],
        dtype=np.float64,
    )
    rng = np.random.default_rng(4)
    inputs["radii"] = (
        100.0 / coef
        + 1.5 * inputs["sigmas"]
        + rng.normal(0.0, 0.5, n_points)
    )

    _, diameter_plain, debug_plain = get_nozzle_end_home_position(**inputs)
    _, diameter_boot, debug_boot = get_nozzle_end_home_position(
        **inputs,
        n_sigma_bootstrap=400,
        n_sigma_bootstrap_seed=7,
    )

    assert diameter_boot == pytest.approx(diameter_plain)
    assert debug_boot["n_sigma_estimation"]["n_sigma_opt"] == pytest.approx(
        debug_plain["n_sigma_estimation"]["n_sigma_opt"]
    )
    confidence = debug_boot["n_sigma_estimation"]["confidence"]
    assert confidence is not None
    assert confidence["method"] == "bootstrap"
    assert confidence["n_bootstrap"] == 400
    assert confidence["n_valid"] == 400
    n_sigma_opt = debug_boot["n_sigma_estimation"]["n_sigma_opt"]
    assert confidence["ci_low"] <= confidence["ci_high"]
    assert confidence["ci_low"] <= n_sigma_opt <= confidence["ci_high"]
    assert confidence["continuous_ci_low"] <= confidence["continuous_opt"]
    assert confidence["continuous_opt"] <= confidence["continuous_ci_high"]
    assert abs(n_sigma_opt - 1.5) < 0.25


def test_nozzle_end_home_position_rejects_invalid_n_sigma_bootstrap() -> None:
    inputs = _nozzle_inputs()

    for value in (-1, 1):
        with pytest.raises(ValueError, match="n_sigma_bootstrap"):
            get_nozzle_end_home_position(
                **inputs,
                n_sigma_bootstrap=value,
            )


def test_nozzle_end_home_position_caps_n_sigma() -> None:
    n_points = 24
    robot_positions = np.column_stack(
        [
            np.linspace(-40.0, 40.0, n_points),
            np.linspace(-20.0, 20.0, n_points),
            np.linspace(0.0, 80.0, n_points),
        ]
    )
    image_center_points = np.column_stack(
        [
            1200.0 + 0.2 * robot_positions[:, 0],
            1000.0 + 0.3 * robot_positions[:, 1],
        ]
    )
    inputs = {
        "sphere_home_position": np.array([10.0, 20.0, 30.0]),
        "robot_positions": robot_positions,
        "image_center_points": image_center_points,
        "intrinsic_matrix": np.array(
            [
                [2000.0, 0.0, 1224.0],
                [0.0, 2000.0, 1024.0],
                [0.0, 0.0, 1.0],
            ]
        ),
        "extrinsic_matrix": np.eye(4),
        "distortion": np.zeros(5),
        "sigmas": np.linspace(1.0, 5.0, n_points),
        "radii": np.full(n_points, 100.0),
        "all_directions": np.ones(n_points),
    }

    _, _, first_debug = get_nozzle_end_home_position(**inputs)
    coef = np.asarray(
        first_debug["sphere_radius_estimation"]["coef_for_radii"],
        dtype=np.float64,
    )
    # Put a known 1.5 sigma outward bias into the raw radii. The empirical
    # optimum should be near 1.5, so the 0.5 cap must change the diameter.
    inputs["radii"] = 100.0 / coef + 1.5 * inputs["sigmas"]

    _, diameter_opt, debug_opt = get_nozzle_end_home_position(**inputs)
    _, diameter_cap, debug_cap = get_nozzle_end_home_position(
        **inputs,
        max_n_sigma=0.5,
    )

    assert debug_opt["sphere_radius_estimation"]["n_sigma_est"] > 0.5
    assert debug_cap["sphere_radius_estimation"]["n_sigma_est"] == 0.5
    assert diameter_cap > diameter_opt


def _nozzle_inputs() -> dict:
    n_points = 24
    robot_positions = np.column_stack(
        [
            np.linspace(-40.0, 40.0, n_points),
            np.linspace(-20.0, 20.0, n_points),
            np.linspace(0.0, 80.0, n_points),
        ]
    )
    image_center_points = np.column_stack(
        [
            1200.0 + 0.2 * robot_positions[:, 0],
            1000.0 + 0.3 * robot_positions[:, 1],
        ]
    )
    return {
        "sphere_home_position": np.array([10.0, 20.0, 30.0]),
        "robot_positions": robot_positions,
        "image_center_points": image_center_points,
        "intrinsic_matrix": np.array(
            [
                [2000.0, 0.0, 1224.0],
                [0.0, 2000.0, 1024.0],
                [0.0, 0.0, 1.0],
            ]
        ),
        "extrinsic_matrix": np.eye(4),
        "distortion": np.zeros(5),
        "sigmas": np.ones(n_points),
        "radii": np.full(n_points, 100.0),
        "all_directions": np.ones(n_points),
    }


def test_nozzle_end_home_position_rejects_mixed_directions() -> None:
    inputs = _nozzle_inputs()
    inputs["all_directions"] = np.array([1.0, -1.0] + [1.0] * 22)

    with pytest.raises(ValueError, match="consistent"):
        get_nozzle_end_home_position(**inputs)


def test_nozzle_end_home_position_rejects_empty_directions() -> None:
    inputs = _nozzle_inputs()
    inputs["all_directions"] = np.array([], dtype=np.float64)

    with pytest.raises(ValueError, match="at least one"):
        get_nozzle_end_home_position(**inputs)


def test_nozzle_end_home_position_rejects_nonpositive_sphere_radius() -> None:
    inputs = _nozzle_inputs()
    inputs["radii"] = np.zeros_like(inputs["radii"])

    with pytest.raises(ValueError, match="finite and positive"):
        get_nozzle_end_home_position(**inputs)


def test_nozzle_end_home_position_rejects_invalid_n_sigma_cap() -> None:
    inputs = _nozzle_inputs()

    with pytest.raises(ValueError, match="max_n_sigma"):
        get_nozzle_end_home_position(**inputs, max_n_sigma=-0.1)
