# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for the optional Matplotlib reporting helpers."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg", force=True)

import station_calibration.plots as plots  # noqa: E402


def _plot_data() -> dict[str, object]:
    n_points = 6
    robot_positions = np.column_stack(
        [
            np.linspace(-10.0, 10.0, n_points),
            np.linspace(-5.0, 5.0, n_points),
            np.linspace(0.0, 50.0, n_points),
        ]
    )
    center_points = np.column_stack(
        [
            np.linspace(500.0, 700.0, n_points),
            np.linspace(400.0, 600.0, n_points),
        ]
    )
    radii = np.linspace(90.0, 110.0, n_points)
    sigmas = np.linspace(0.8, 1.2, n_points)
    debug_data = [
        ["N", "N_reduced", "fx", "dfx", "fy", "dfy", "t3", "dt3", "n params", "RMSE"],
        [1, 1, 1000.0, 1.0, 1000.0, 1.0, 80.0, 1.0, 8, 0.1],
        [2, 2, 1001.0, 1.0, 1001.0, 1.0, 81.0, 1.0, 8, 0.2],
        [3, 3, 1002.0, 1.0, 1002.0, 1.0, 82.0, 1.0, 8, 0.3],
    ]
    return {
        "robot_positions": robot_positions,
        "center_points": center_points,
        "radii": radii,
        "sigmas": sigmas,
        "debug_data": debug_data,
    }


def test_visualize_results_writes_all_reporting_plots(tmp_path: Path) -> None:
    data = _plot_data()
    center_points = data["center_points"]
    sigmas = data["sigmas"]
    radii = data["radii"]
    debug_data = data["debug_data"]
    n_points = len(radii)
    coef_for_radii = np.linspace(0.01, 0.02, n_points)
    debug_nozzle = {
        "scaling_visualization": {
            "z_pos": np.linspace(0.0, 50.0, n_points),
            "scale": coef_for_radii,
            "fit_popt": np.array([1e-4, 1e-2, 1e-3]),
        },
        "n_sigma_estimation": {
            "n_sigmas": np.linspace(0.0, 4.0, 100),
            "std_radii": np.linspace(1.0, 0.1, 100),
            "confidence": {
                "ci_low": 0.5,
                "ci_high": 0.8,
            },
        },
        "sphere_radius_estimation": {
            "z_pos": np.linspace(0.0, 50.0, n_points),
            "radii": radii,
            "sigmas": sigmas,
            "coef_for_radii": coef_for_radii,
            "n_sigma_est": 1.0,
        },
        "sphere_radius_vs_depth": {
            "z_pos": np.linspace(0.0, 50.0, n_points),
            "radii": radii,
            "sigmas": sigmas,
            "coef_for_radii": coef_for_radii,
            "n_sigma_est": 1.0,
        },
    }

    plots.visualize_results(
        rel_robot_positions=data["robot_positions"],
        center_points_adjusted=center_points,
        extrinsic_matrix=np.eye(4),
        intrinsic_matrix=np.array(
            [[1000.0, 0.0, 600.0], [0.0, 1000.0, 450.0], [0.0, 0.0, 1.0]]
        ),
        radii=radii,
        sigmas=sigmas,
        image_size_xy=(1200, 900),
        back_projected_home_pos=np.array([600.0, 450.0]),
        closest_image_arg=0,
        n_distortion_coefs=4,
        debug_nozzle_and_home_pos=debug_nozzle,
        residuals=np.linspace(-1.0, 1.0, 2 * n_points),
        all_debug_data_to_store=debug_data,
        debug_folder=tmp_path,
    )

    assert (tmp_path / "radii_in_depth.png").is_file()
    assert (tmp_path / "sigmas_in_depth.png").is_file()
    assert (tmp_path / "center_points_04.png").is_file()
    assert (tmp_path / "scale_coef_estimation.png").is_file()
    assert (tmp_path / "n_sigma_estimation.png").is_file()
    assert (tmp_path / "sphere_diam_estimation.png").is_file()
    assert (tmp_path / "sphere_diam_vs_depth.png").is_file()
    assert (tmp_path / "sphere_diam_rel_error_vs_depth.png").is_file()
    assert (tmp_path / f"2D redidual vectors - {n_points} points.png").is_file()
    assert (tmp_path / "focal length vs number of points.png").is_file()
    assert (tmp_path / "focal length vs left number of points.png").is_file()
    assert (tmp_path / "camera distance vs number of points.png").is_file()
    assert (tmp_path / "camera distance vs left number of points.png").is_file()
    assert (tmp_path / "RMSE vs number of points.png").is_file()


def test_visualize_image_center_points_without_optional_overlays(
    tmp_path: Path,
) -> None:
    data = _plot_data()

    plots.visualize_image_center_points(
        center_points=data["center_points"],
        sigmas=data["sigmas"],
        image_size_xy=(1200, 900),
        camera_principal_point=np.array([600.0, 450.0]),
        nozzle_home_pos=None,
        closest_image_arg=None,
        n_distortion_coefs=0,
        debug_folder=tmp_path,
    )

    assert (tmp_path / "center_points_00.png").is_file()
