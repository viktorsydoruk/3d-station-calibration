"""3D Station calibration routine

    The new automatic routine to calibrate 3D stations in phenoSeeder. A white ball (preferable POM) is placed at
    different positions in front of the camera. Using the images intrinsic and extrinsic matrices can be calculated.

    Copyright 2026 Forschungszentrum Jülich GmbH

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

__author__ = "Viktor Sydoruk"
__copyright__ = "Copyright 2026, Forschungszentrum Jülich GmbH"
__credits__ = ["Viktor Sydoruk", "Andreas Fischbach", "ChatGPT"]
__license__ = "Apache 2"
__version__ = "2026.08"
__maintainer__ = "Viktor Sydoruk"
__email__ = "v.sydoruk@fz-juelich.de"
__status__ = "Developments"
__date__ = "25.08.2026"


import numpy as np
import traceback

from _3dsc_libs import (load_robot_positions, search_images, get_sphere_centers_and_blur_sigmas, calibrate_camera,
                        get_calibration, print_calibration, adjust_image_center_points, store_all_points,
                        load_all_points, visualize_image_center_points, visualize_radii, visualize_sigmas, Settings,
                        find_robot_home_pos_shift, get_nozzle_end_home_position, visualize_nozzle_and_home_pos_estimation,
                        DebugInfo, check_distortion_monotonicity)


def main(folder_to_analyze: str, **opts) -> None:
    settings = Settings(folder_to_analyze, **opts)
    print_debug = DebugInfo(settings.debug)

    try:
        print_debug()
        print_debug(f"Analysis of {settings.main_folder}")

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
                patterns=settings.imagenames_patterns,
                sort_by_mtime=settings.sort_imagenames_by_mtime,
            )
            print_debug(len(all_images_filenames), "images are found")

            center_points, sigmas, radii, image_sizes, all_directions = get_sphere_centers_and_blur_sigmas(
                all_images_filenames,
                bg_height_px=settings.bg_height_pxs,
                bg_color_est_perc=settings.bg_color_est_perc,
                n_mov_aver=settings.n_move_aver,
                sphere_center_to_nozzle_part=settings.sphere_center_to_nozzle_part,
                min_bg_pixels_on_edges=settings.min_bg_pixels_on_edges,
                blur_est_border_thickness=settings.blur_est_border_thickness,
                print_debug=print_debug,
                debug_folder=settings.debug_folder,
                store_debug_images=settings.store_debug_images
            )

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

        image_size_xy = tuple(np.flip(np.nanmax(image_sizes, axis=0)).astype(int))  # a tuple (size_x, size_y)
        # first estimation of the home position for the robotic arm, where the seed should be delivered
        pos_home = robot_positions.mean(axis=0)

        # select suitable data
        rel_robot_positions = robot_positions[mask] - pos_home
        center_points = center_points[mask]
        radii = radii[mask]
        sigmas = sigmas[mask]
        center_points_adjusted = np.copy(center_points)

        for _ in range(settings.n_iterations):

            # calibration of the camera (estimation of intrinsic, extrinsic, distortion parameters)
            result = calibrate_camera(
                rel_robot_positions,
                center_points_adjusted,
                radii,
                sigmas,
                focal_length_initial=2000.0,
                camera_distance_initial=80.0,
                image_size_xy=image_size_xy,
                fix_cx_cy=settings.fix_cx_cy,
                n_distortion_coefs=settings.n_distortion_coefs,
                debug=settings.debug,
            )

            # extract the camere matrices from the fit result
            intrinsic_matrix, distortion, rvec, extrinsic_matrix = get_calibration(
                result,
                image_size_xy=image_size_xy,
                fix_cx_cy=settings.fix_cx_cy,
                n_distortion_coefs = settings.n_distortion_coefs,
            )

            # estimation the shift of the home position based on bluring and cx, cy
            pos_home_shift = find_robot_home_pos_shift(
                rel_robot_positions,
                center_points_adjusted,
                intrinsic_matrix=intrinsic_matrix,
                extrinsic_matrix=extrinsic_matrix,
                distortion=distortion,
                sigmas=sigmas,
            )

            pos_home += pos_home_shift
            rel_robot_positions -= pos_home_shift

            center_points_adjusted = adjust_image_center_points(
                center_points,
                radii,
                intrinsic_matrix,
            )

            # distortion coefs should give monotonic function 1 + k1*r**2 + k2*r**4 + k3*r**6
            if not check_distortion_monotonicity(distortion, intrinsic_matrix, image_size_xy):
                print_debug("distortion doesn't show monotonic behaviour, and should be neglected")
                settings.n_distortion_coefs = 0

        # calculating the nozzle home position
        nozzle_end_home_pos, sphere_diam_mm, debug_nozzle_and_home_pos = get_nozzle_end_home_position(
            pos_home,
            rel_robot_positions,
            center_points_adjusted,
            intrinsic_matrix=intrinsic_matrix,
            extrinsic_matrix=extrinsic_matrix,
            distortion=distortion,
            sigmas=sigmas,
            radii=radii,
            all_directions=all_directions,
        )

        print_debug(f"Sphere center home position: {pos_home}, estimated sphere diameter: {sphere_diam_mm: 0.3f} mm")
        print_debug(f"Nozzle center home position: {nozzle_end_home_pos}")
        if settings.debug:
            print_calibration(
                result,
                image_size_xy=image_size_xy,
                fix_cx_cy=settings.fix_cx_cy,
                n_distortion_coefs=settings.n_distortion_coefs
            )
            visualize_radii(
                rel_robot_positions,
                extrinsic_matrix,
                radii=radii,
                sigmas=sigmas,
                debug_folder=settings.debug_folder,
            )

            visualize_sigmas(
                rel_robot_positions,
                extrinsic_matrix,
                sigmas=sigmas,
                debug_folder=settings.debug_folder,
            )

            visualize_image_center_points(
                center_points_adjusted,
                sigmas,
                image_size_xy=image_size_xy,
                camera_principal_point=intrinsic_matrix[:2, 2],
                infinity_point=None,
                n_distortion_coefs=settings.n_distortion_coefs,
                debug_folder=settings.debug_folder,
            )
            visualize_nozzle_and_home_pos_estimation(debug_nozzle_and_home_pos, debug_folder=settings.debug_folder)

    except KeyboardInterrupt:
        print_debug(">>>> Interrupted by user <<<<")
        exit()
    except Exception:
        traceback.print_exc()
