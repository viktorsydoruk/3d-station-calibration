# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Camera-model estimation, fitting, and diagnostics."""

__all__ = [
    "print_calibration",
    "get_calibration",
    "calibrate_camera",
    "check_distortion_monotonicity",
    "back_projected_point",
    "calculate_RMSE",
    "calculate_calibration_errors",
    "calculate_outlier_scores",
    "chi_square_threshold",
    "is_spatially_clustered",
]

from .fit import calibrate_camera
from .metrics import (
    back_projected_point,
    calculate_RMSE,
    calculate_calibration_errors,
    check_distortion_monotonicity,
    print_calibration,
)
from .outliers import (
    calculate_outlier_scores,
    chi_square_threshold,
    is_spatially_clustered,
)
from .model import get_calibration
