# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Regression test for the production pinhole fit on the ceramic-ball folder.

The fixture is the stored point cache of
``P:\\3Dcalibration\\3D_small_20260929_ceramic`` (500 rows, 489 valid) including
the per-centre covariance columns. The expected values are the stored
``output/calibration_data.yaml`` of that folder. The convergence-aware loop
changes them by less than 2e-8 relative, so the same tolerances as the other
real-data regression tests apply.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from station_calibration import DebugInfo, Settings, create_folder_session

DATA_FILE = Path(__file__).parent / "data" / "CeramicAllPoints.dat"

EXPECTED_POS_HOME = np.array(
    [315.49392483110137, -111.57585041595257, -35.05526817595112]
)
EXPECTED_INTRINSIC = np.array(
    [
        [22226.476920472956, 0.0, 1224.0],
        [0.0, 22062.000199258277, 1024.0],
        [0.0, 0.0, 1.0],
    ]
)
EXPECTED_EXTRINSIC = np.array(
    [
        [0.9999331121196744, 0.010666024484365166, -0.004472941801825602,
         -0.0008913618940464136],
        [0.004483334424173545, -0.0009506556808867737, 0.9999894979279621,
         -0.002779692124568651],
        [0.01066166024147349, -0.9999426644440549, -0.0009984114482831914,
         74.38554065147301],
        [0.0, 0.0, 0.0, 1.0],
    ]
)
EXPECTED_RMSE = 4.554734378003199


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        tmp_path,
        debug=False,
        load_stored_data=True,
        n_iterations=3,
        center_shift_tolerance=0.01,
        allowed_outliers=10,
        fix_cx_cy=True,
        n_distortion_coefs=0,
        focal_length_initial=2000.0,
        camera_distance_initial=80.0,
        center_weighting=True,
    )


def test_ceramic_pinhole_regression_matches_stored_calibration(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    shutil.copy(DATA_FILE, settings.all_center_points_file)

    session = create_folder_session(settings, DebugInfo(False), fit_every_n=None)
    result = session.finish()

    assert result.observation_count == 489
    assert int(result.fit_mask.sum()) == 489
    assert int(result.used_mask.sum()) == 489
    assert result.image_size_xy == (2448, 2048)
    assert result.n_distortion_coefs == 0
    assert result.optimize_result.success

    np.testing.assert_allclose(result.distortion, np.zeros(14), atol=0.0)
    np.testing.assert_allclose(
        result.pos_home, EXPECTED_POS_HOME, rtol=1e-6, atol=1e-6
    )
    np.testing.assert_allclose(
        result.intrinsic_matrix, EXPECTED_INTRINSIC, rtol=1e-6
    )
    np.testing.assert_allclose(
        result.extrinsic_matrix, EXPECTED_EXTRINSIC, rtol=1e-5, atol=1e-7
    )
    assert result.rmse == pytest.approx(EXPECTED_RMSE, rel=1e-6)
