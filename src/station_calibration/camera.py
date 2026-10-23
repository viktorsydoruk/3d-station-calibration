# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Deprecated compatibility shim for :mod:`station_calibration.calibration`."""

__all__ = [
    "print_calibration",
    "get_calibration",
    "calibrate_camera",
    "check_distortion_monotonicity",
    "back_projected_point",
    "calculate_RMSE",
    "calculate_calibration_errors",
]

from .calibration import (
    back_projected_point,
    calculate_RMSE,
    calculate_calibration_errors,
    calibrate_camera,
    check_distortion_monotonicity,
    get_calibration,
    print_calibration,
)
from .calibration.initialization import (
    estimate_r_initial,
    extract_z_lines,
    make_initial_parameters,
)
from .calibration.model import (
    params_names,
    project_points,
    residuals,
    unwrap_k_distortion_params,
    unwrap_params,
)
