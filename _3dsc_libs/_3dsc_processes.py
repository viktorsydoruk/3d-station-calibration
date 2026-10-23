"""The complex processes are located here"""

import numpy as np
from scipy.optimize import OptimizeResult
from _3dsc_libs import (Settings, DebugInfo, calibrate_camera, get_calibration, find_robot_home_pos_shift,
                        adjust_image_center_points, check_distortion_monotonicity, calculate_RMSE, load_all_points,
                        load_robot_positions, search_images, get_sphere_centers_and_blur_sigmas, store_all_points)


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
    last_rmse = np.inf
    last_arg = 0

    if settings.allowed_outliers == 0:
        n_out_iter = 1
    elif settings.allowed_outliers < 0:
        raise ValueError("allowed_outliers should be a positive number")
    elif settings.allowed_outliers < 1:
        # Rounding down could give zero iterations for small fractions; the fit
        # must always run at least once.
        n_out_iter = max(1, int(n_points * settings.allowed_outliers))
    else:
        n_out_iter = max(1, int(settings.allowed_outliers))

    # Removing outliers is only possible while min_points measurements remain.
    n_out_iter = min(n_out_iter, n_points - min_points + 1)

    result: OptimizeResult | None = None

    for i in range(n_out_iter):
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

            rmse = calculate_RMSE(result, standardized=False)

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

        pos_shifts = result.fun.reshape(-1, 2)
        pos_shifts_std = np.std(pos_shifts, axis=0)
        possible_outliers = np.abs(pos_shifts) > 2*pos_shifts_std[None, :]
        are_there_outliers = np.any(possible_outliers)

        if are_there_outliers and i < n_out_iter - 1:
            max_arg = np.argmax(np.sum((pos_shifts*possible_outliers)**2, axis=1))
            dmax_arg = np.cumsum(~mask)[mask][max_arg]
            if rmse > last_rmse:
                mask[last_arg] = True
            last_arg = max_arg + dmax_arg
            if np.count_nonzero(mask) > min_points:
                mask[last_arg] = False
            else:
                break
            last_rmse = rmse
        else:
            break

    if result is None:
        raise RuntimeError("Camera calibration did not run")

    return pos_home, center_points_adjusted, intrinsic_matrix, extrinsic_matrix, distortion, result, rmse, mask, n_dist_coefs


def get_3D_and_2D_data(settings: Settings,
                       print_debug: DebugInfo = DebugInfo()) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]:
    """

    :param settings:
    :param print_debug:
    :return:
    """
    # loading stored data (already analyzed) if needed
    if settings.load_stored_data and settings.all_center_points_file.exists():
        robot_positions, center_points, radii, sigmas, image_sizes, all_directions = load_all_points(
            settings.all_center_points_file,
        )

    else:
        # reading the positions of robotic arm
        robot_positions, imagenames = load_robot_positions(settings.robot_pos_file)
        print_debug(len(robot_positions), "robot position coordinates are collected")

        # searching for all images
        all_images_filenames = search_images(
            settings.main_folder,
            imagenames,
            patterns=settings.image_names_patterns,
            sort_by_mtime=settings.sort_imagenames_by_mtime,
        )
        print_debug(len(all_images_filenames), "images are found")

        # getting sphere centers and edge blur sigmas
        center_points, sigmas, radii, image_sizes, all_directions = get_sphere_centers_and_blur_sigmas(
            all_images_filenames,
            bg_height_px=settings.bg_height_pxs,
            bg_color_est_perc=settings.bg_color_est_perc,
            fixed_bg_threshold=settings.fixed_bg_threshold,
            n_mov_aver=settings.n_move_aver,
            sphere_center_to_nozzle_part=settings.sphere_center_to_nozzle_part,
            min_bg_pixels_on_edges=settings.min_bg_pixels_on_edges,
            blur_est_border_thickness=settings.blur_est_border_thickness,
            print_debug=print_debug,
            debug_folder=settings.debug_folder,
            store_debug_images=settings.store_debug_images
        )

        # storing all points
        store_all_points(
            settings.all_center_points_file,
            robot_positions,
            center_points,
            radii,
            sigmas,
            image_sizes,
            all_directions,
        )

    # creating mask where the spheres were recognized
    mask = np.logical_and(~np.isnan(sigmas), ~np.isnan(radii))

    image_size_xy = np.flip(np.nanmax(image_sizes, axis=0)).astype(int).tolist()  # a tuple (size_x, size_y)

    center_points = center_points[mask]
    radii = radii[mask]
    sigmas = sigmas[mask]
    robot_positions = robot_positions[mask]
    all_directions = all_directions[mask]

    return robot_positions, center_points, radii, sigmas, all_directions, image_size_xy

