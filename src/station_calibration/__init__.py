# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""3D station calibration library.

The package is arranged around a source-agnostic calibration session. Folder and
Ice frontends analyze images, produce observations, and feed them into the same
session. Image analysis lives in :mod:`station_calibration.vision`, the camera
model and fit in :mod:`station_calibration.calibration`, and input/output in
:mod:`station_calibration.storage`. The iterative pipeline remains in
:mod:`station_calibration.processes`.

The public API is re-exported here explicitly so callers do not depend on the
internal module layout.
"""

from importlib.metadata import PackageNotFoundError, version as _distribution_version

try:
    __version__ = _distribution_version("3dstationcalibration")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0+unknown"

__all__ = [
    "__version__",
    # Settings and lifecycle
    "Settings",
    "PossibleOptions",
    "DebugInfo",
    "StopPolicy",
    "StopReason",
    "StopStatus",
    "DEFAULT_TARGET_OBSERVATIONS",
    "FitSnapshot",
    "ReadinessPolicy",
    "ReadinessStatus",
    "ReadinessTolerances",
    # Domain models and session
    "CalibrationObservation",
    "ObservationRejection",
    "CalibrationResult",
    "SIGMA_OFFSET",
    "CalibrationSession",
    "CalibrationService",
    # Sources
    "ObservationDataset",
    "ObservationSource",
    "FolderDataset",
    "FolderCalibrationSource",
    "create_folder_session",
    "observations_to_arrays",
    # Image analysis
    "SphereObservation",
    "ImageAnalysisResult",
    "load_image",
    "decode_image",
    "split_image",
    "analyze_image",
    "analyze_image_array",
    "analyze_image_bytes",
    "analyze_images",
    "get_sphere_centers_and_blur_sigmas",
    "get_radius_outlier_mask",
    "filtering_data_by_radius",
    "adjust_image_center_points",
    # Numerical pipeline
    "get_calibration_data",
    "get_3D_and_2D_data",
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
    # Robot and geometry helpers
    "find_robot_home_pos_shift",
    "get_nozzle_end_home_position",
    "find_proper_args_to_compare",
    "fit_line_general_form",
    "intersect_lines",
    "calculate_errors",
    # File and output helpers
    "load_robot_positions",
    "search_images",
    "store_all_points",
    "load_all_points",
    "load_all_points_with_covariances",
    "RESULT_SCHEMA_VERSION",
    "calibration_document",
    "store_calibration",
    # Reporting
    "apply_own_style_to_mpl",
    "visualize_image_center_points",
    "visualize_radii",
    "visualize_sigmas",
    "visualize_nozzle_and_home_pos_estimation",
    "visualize_scale_coef_estimation",
    "visualize_n_sigma_estimation",
    "visualize_sphere_radius_estimation",
    "visualize_sphere_radius_vs_depth",
    "visualize_residuals",
    "visualize_debug_data",
    "visualize_results",
]

from .calibration import (
    back_projected_point,
    calculate_RMSE,
    calculate_calibration_errors,
    calculate_outlier_scores,
    calibrate_camera,
    check_distortion_monotonicity,
    chi_square_threshold,
    get_calibration,
    is_spatially_clustered,
    print_calibration,
)
from .debug import DebugInfo
from .models import (
    SIGMA_OFFSET,
    CalibrationObservation,
    CalibrationResult,
    ObservationRejection,
)
from .storage import (
    RESULT_SCHEMA_VERSION,
    calibration_document,
    load_all_points,
    load_all_points_with_covariances,
    load_robot_positions,
    search_images,
    store_all_points,
    store_calibration,
)
from .vision import (
    ImageAnalysisResult,
    SphereObservation,
    adjust_image_center_points,
    analyze_image,
    analyze_image_array,
    analyze_image_bytes,
    analyze_images,
    decode_image,
    filtering_data_by_radius,
    get_radius_outlier_mask,
    get_sphere_centers_and_blur_sigmas,
    load_image,
    split_image,
)
from .processes import get_3D_and_2D_data, get_calibration_data
from .readiness import (
    FitSnapshot,
    ReadinessPolicy,
    ReadinessStatus,
    ReadinessTolerances,
)
from .robot import find_robot_home_pos_shift, get_nozzle_end_home_position
from .service import CalibrationService
from .session import CalibrationSession
from .settings import PossibleOptions, Settings
from .sources.base import ObservationDataset, ObservationSource
from .sources.folder import (
    FolderCalibrationSource,
    FolderDataset,
    create_folder_session,
    observations_to_arrays,
)
from .stop import (
    DEFAULT_TARGET_OBSERVATIONS,
    StopPolicy,
    StopReason,
    StopStatus,
)
from .support import (
    calculate_errors,
    find_proper_args_to_compare,
    fit_line_general_form,
    intersect_lines,
)


_PLOTTING_NAMES = {
    "apply_own_style_to_mpl",
    "visualize_debug_data",
    "visualize_image_center_points",
    "visualize_n_sigma_estimation",
    "visualize_nozzle_and_home_pos_estimation",
    "visualize_radii",
    "visualize_residuals",
    "visualize_results",
    "visualize_scale_coef_estimation",
    "visualize_sigmas",
    "visualize_sphere_radius_estimation",
    "visualize_sphere_radius_vs_depth",
}


def __getattr__(name: str):
    """Import plotting helpers lazily so headless callers do not load pyplot."""
    if name in _PLOTTING_NAMES:
        from . import plots

        return getattr(plots, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
