# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""The complex processes are located here"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import OptimizeResult

from .calibration import (
    calculate_RMSE,
    calibrate_camera,
    check_distortion_monotonicity,
    get_calibration,
)
from .debug import DebugInfo
from .vision import adjust_image_center_points
from .robot import find_robot_home_pos_shift
from .settings import Settings


@dataclass
class _FitState:
    """One candidate fit kept while the outlier loop evaluates removals."""
    pos_home: np.ndarray
    center_points_adjusted: np.ndarray
    intrinsic_matrix: np.ndarray
    extrinsic_matrix: np.ndarray
    distortion: np.ndarray
    result: OptimizeResult
    rmse: float
    mask: np.ndarray
    n_dist_coefs: int


def _fit_camera(rel_robot_positions: np.ndarray,
                center_points: np.ndarray,
                radii: np.ndarray,
                sigmas: np.ndarray,
                mask: np.ndarray,
                image_size_xy: tuple[int, int],
                settings: Settings,
                focal_length_initial: float,
                camera_distance_initial: float,
                n_distortion_coefs: int
                ) -> tuple[OptimizeResult, np.ndarray, np.ndarray, np.ndarray]:
    """Run one calibration fit and unwrap the resulting camera model."""
    result = calibrate_camera(
        rel_robot_positions[mask],
        center_points[mask],
        radii[mask],
        sigmas[mask],
        focal_length_initial=focal_length_initial,
        camera_distance_initial=camera_distance_initial,
        image_size_xy=image_size_xy,
        fix_cx_cy=settings.fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs,
    )
    intrinsic_matrix, distortion, _, extrinsic_matrix = get_calibration(
        result.x,
        image_size_xy=image_size_xy,
        fix_cx_cy=settings.fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs,
    )
    return result, intrinsic_matrix, distortion, extrinsic_matrix


def _fit_camera_with_distortion_fallback(rel_robot_positions: np.ndarray,
                                         center_points: np.ndarray,
                                         radii: np.ndarray,
                                         sigmas: np.ndarray,
                                         mask: np.ndarray,
                                         image_size_xy: tuple[int, int],
                                         settings: Settings,
                                         focal_length_initial: float,
                                         camera_distance_initial: float,
                                         n_distortion_coefs: int,
                                         print_debug: DebugInfo
                                         ) -> tuple[OptimizeResult, np.ndarray, np.ndarray, np.ndarray, int]:
    """Fit the camera and refit without distortion if the model is not monotonic."""
    result, intrinsic_matrix, distortion, extrinsic_matrix = _fit_camera(
        rel_robot_positions,
        center_points,
        radii,
        sigmas,
        mask,
        image_size_xy,
        settings,
        focal_length_initial,
        camera_distance_initial,
        n_distortion_coefs,
    )

    if n_distortion_coefs != 0 and not check_distortion_monotonicity(
        distortion, intrinsic_matrix, image_size_xy
    ):
        print_debug("distortion doesn't show monotonic behaviour, and should be neglected")
        n_distortion_coefs = 0
        result, intrinsic_matrix, distortion, extrinsic_matrix = _fit_camera(
            rel_robot_positions,
            center_points,
            radii,
            sigmas,
            mask,
            image_size_xy,
            settings,
            focal_length_initial,
            camera_distance_initial,
            n_distortion_coefs,
        )

    return result, intrinsic_matrix, distortion, extrinsic_matrix, n_distortion_coefs


def get_calibration_data(robot_positions: np.ndarray,
                         center_points: np.ndarray,
                         radii: np.ndarray,
                         sigmas: np.ndarray,
                         image_size_xy: tuple[int, int],
                         settings: Settings,
                         print_debug: DebugInfo = DebugInfo()
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, OptimizeResult, float, np.ndarray, int]:
    # first estimation of the home position for the robotic arm, where the seed should be delivered
    pos_home = robot_positions.mean(axis=0)
    n_points = len(robot_positions)
    min_points = 10 + settings.n_distortion_coefs

    if n_points < min_points:
        raise ValueError(
            f"At least {min_points} valid measurements are required, got {n_points}"
        )

    # initial parameters
    rel_robot_positions = robot_positions - pos_home
    center_points_adjusted = np.copy(center_points)
    n_dist_coefs = settings.n_distortion_coefs

    mask = np.ones(n_points, dtype=bool)

    if settings.allowed_outliers == 0:
        max_removals = 0
    elif settings.allowed_outliers < 0:
        raise ValueError("allowed_outliers should be a positive number")
    elif settings.allowed_outliers < 1:
        max_removals = int(n_points * settings.allowed_outliers)
    else:
        max_removals = int(settings.allowed_outliers)

    # Removing outliers is only possible while min_points measurements remain.
    max_removals = min(max_removals, n_points - min_points)
    best: _FitState | None = None

    for removal_index in range(max_removals + 1):
        focal_length_initial = settings.focal_length_initial
        camera_distance_initial = settings.camera_distance_initial
        for _ in range(settings.n_iterations):

            # calibration of the camera (estimation of intrinsic, extrinsic, distortion parameters)
            result, intrinsic_matrix, distortion, extrinsic_matrix, n_dist_coefs = (
                _fit_camera_with_distortion_fallback(
                    rel_robot_positions,
                    center_points_adjusted,
                    radii,
                    sigmas,
                    mask,
                    image_size_xy,
                    settings,
                    focal_length_initial,
                    camera_distance_initial,
                    n_dist_coefs,
                    print_debug,
                )
            )

            # estimation the shift of the home position based on bluring and cx, cy
            pos_home_shift = find_robot_home_pos_shift(
                rel_robot_positions[mask],
                center_points_adjusted[mask],
                intrinsic_matrix=intrinsic_matrix,
                extrinsic_matrix=extrinsic_matrix,
                distortion=distortion,
                sigmas=sigmas[mask],
            )

            pos_home += pos_home_shift
            rel_robot_positions -= pos_home_shift

            center_points_adjusted = adjust_image_center_points(
                center_points,
                radii,
                intrinsic_matrix,
            )

            focal_length_initial = intrinsic_matrix[0, 0]
            camera_distance_initial = extrinsic_matrix[2, 3]

        # The loop above adjusts the center points after the last fit. Refit once
        # more so that the returned matrices and error correspond to the points
        # that are returned as well.
        result, intrinsic_matrix, distortion, extrinsic_matrix, n_dist_coefs = (
            _fit_camera_with_distortion_fallback(
                rel_robot_positions,
                center_points_adjusted,
                radii,
                sigmas,
                mask,
                image_size_xy,
                settings,
                focal_length_initial,
                camera_distance_initial,
                n_dist_coefs,
                print_debug,
            )
        )

        rmse = calculate_RMSE(result, standardized=False)
        if (
            best is None
            or rmse < best.rmse
            or (np.isfinite(rmse) and not np.isfinite(best.rmse))
        ):
            best = _FitState(
                pos_home=pos_home.copy(),
                center_points_adjusted=center_points_adjusted.copy(),
                intrinsic_matrix=intrinsic_matrix.copy(),
                extrinsic_matrix=extrinsic_matrix.copy(),
                distortion=distortion.copy(),
                result=result,
                rmse=rmse,
                mask=mask.copy(),
                n_dist_coefs=n_dist_coefs,
            )

        if removal_index == max_removals:
            break

        pos_shifts = result.fun.reshape(-1, 2)
        pos_shifts_std = np.std(pos_shifts, axis=0)
        possible_outliers = np.abs(pos_shifts) > 2*pos_shifts_std[None, :]
        if not np.any(possible_outliers):
            break

        if np.count_nonzero(mask) <= min_points:
            break

        max_arg = np.argmax(np.sum((pos_shifts*possible_outliers)**2, axis=1))
        dmax_arg = np.cumsum(~mask)[mask][max_arg]
        mask[max_arg + dmax_arg] = False

    if best is None:
        raise RuntimeError("Camera calibration did not run")

    return (
        best.pos_home,
        best.center_points_adjusted,
        best.intrinsic_matrix,
        best.extrinsic_matrix,
        best.distortion,
        best.result,
        best.rmse,
        best.mask,
        best.n_dist_coefs,
    )


def get_3D_and_2D_data(settings: Settings,
                       print_debug: DebugInfo = DebugInfo()) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]:
    """
        Compatibility wrapper around the folder source adapter.

        New code should use :func:`create_folder_session` so the fit is performed by
        :class:`CalibrationSession`; this function remains for callers that only need
        the filtered arrays.
    """
    from .sources.folder import FolderCalibrationSource, observations_to_arrays

    dataset = FolderCalibrationSource(settings, print_debug).load()
    robot_positions, center_points, radii, sigmas, all_directions = (
        observations_to_arrays(dataset.fit_observations)
    )
    return (
        robot_positions,
        center_points,
        radii,
        sigmas,
        all_directions,
        dataset.image_size_xy,
    )
