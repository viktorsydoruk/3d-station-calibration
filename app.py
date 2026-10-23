#!/usr/bin/env python3
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
__contributors__ = ["Viktor Sydoruk", "Blablador"]
__copyright__ = "Copyright 2026, Forschungszentrum Jülich GmbH"
__credits__ = ["Viktor Sydoruk", "Andreas Fischbach", "Blablador"]
__license__ = "Apache 2"
__version__ = "2026.10.23.0"
__maintainer__ = "Viktor Sydoruk"
__email__ = "v.sydoruk@fz-juelich.de"
__status__ = "Developments"
__date__ = "01.10.2026"


import numpy as np
import traceback

from _3dsc_libs import (print_calibration, visualize_results, Settings, get_nozzle_end_home_position,
                        DebugInfo, back_projected_point, calculate_errors, get_calibration_data, get_3D_and_2D_data,
                        store_calibration, calculate_calibration_errors)


def main(folder_to_analyze: str, **opts) -> None:
    settings = Settings(folder_to_analyze, **opts)
    print_debug = DebugInfo(settings.debug)

    print_debug(f"{'':=>100}")
    print_debug(f"{f' Analysis of {settings.main_folder} ':-^100}")
    print_debug(f"{'':=>100}")

    try:
        # getting all the data
        robot_positions, center_points, radii, sigmas, all_directions, image_size_xy = (
            get_3D_and_2D_data(
                settings,
                print_debug
            )
        )

        step_size = 20
        print_debug.debug = False
        all_debug_data_to_store: list[list[str | float| np.floating | np.integer]] = [
            ["N", "N_reduced", "fx", "dfx", "fy", "dfy", "t3", "dt3", "n params", "RMSE"]
        ]
        for i in range(1, len(robot_positions) // step_size, 1):
            if i * step_size < 14:
                continue

            pos_home, center_points_adjusted, intrinsic_matrix, extrinsic_matrix, distortion, result, rmse, mask, _ = (
                get_calibration_data(
                    robot_positions[:i * step_size],
                    center_points[:i * step_size],
                    radii[:i * step_size],
                    sigmas[:i * step_size],
                    image_size_xy,
                    settings,
                    print_debug
                )
            )
            err = calculate_errors(result)
            val = result.x
            print_debug(f"{i*step_size:>3d}. {val[-1]:0.5f} +/- {err[-1]:0.5f}",
                        f"RMSE: {rmse:0.6f}", len(result.x), f"left: {np.count_nonzero(mask)}", print_anyway=True)
            all_debug_data_to_store.append(
                [len(mask), np.count_nonzero(mask), val[0], err[0], val[1], err[1], val[-1], err[-1], len(result.x), rmse]
            )

        print_debug.debug = settings.debug
        # calibrating the camera
        pos_home, center_points_adjusted, intrinsic_matrix, extrinsic_matrix, distortion, result, rmse, mask, n_dist_coef = (
            get_calibration_data(
                robot_positions,
                center_points,
                radii,
                sigmas,
                image_size_xy,
                settings,
                print_debug
            )
        )

        rel_robot_positions = robot_positions - pos_home

        # calculating the nozzle home position
        nozzle_end_home_pos, sphere_diam_mm, debug_nozzle_and_home_pos = (
            get_nozzle_end_home_position(
                sphere_home_position=pos_home,
                robot_positions=rel_robot_positions,
                image_center_points=center_points_adjusted,
                intrinsic_matrix=intrinsic_matrix,
                extrinsic_matrix=extrinsic_matrix,
                distortion=distortion,
                sigmas=sigmas,
                radii=radii,
                all_directions=all_directions,
            )
        )
        intrinsic_std, distortion_std, rot_vec_std, tra_vec_std = calculate_calibration_errors(
            result,
            fix_cx_cy=settings.fix_cx_cy,
            n_distortion_coefs=n_dist_coef,
        )

        store_calibration(
            nozzle_home_position=nozzle_end_home_pos,
            intrinsic_matrix=intrinsic_matrix,
            extrinsic_matrix=extrinsic_matrix,
            distortion_coefficients=distortion,
            intrinsic_std=intrinsic_std,
            rot_vec_std=rot_vec_std,
            tra_vec_std=tra_vec_std,
            distortion_std=distortion_std,
            image_xy=image_size_xy,
            output_folder=settings.output_folder,
        )

        if settings.debug:
            print_debug(f"Sphere center home position: {pos_home}, estimated sphere diameter: {sphere_diam_mm: 0.3f} mm")
            print_debug(f"Nozzle center home position: {nozzle_end_home_pos}")

            closest_image_arg = int(np.argmin(np.sqrt(np.sum((robot_positions[mask]-nozzle_end_home_pos[None, :])**2, axis=1))))

            print_debug(f"Closest to the center image: {closest_image_arg}")
            print_calibration(
                result,
                image_size_xy=image_size_xy,
                fix_cx_cy=settings.fix_cx_cy,
                n_distortion_coefs=n_dist_coef
            )
            back_projected_home_pos = back_projected_point(
                nozzle_end_home_pos - pos_home,
                intrinsic_matrix,
                extrinsic_matrix,
                distortion
            )[0]
            print_debug(back_projected_home_pos)

            visualize_results(
                rel_robot_positions=rel_robot_positions[mask],
                center_points_adjusted=center_points_adjusted[mask],
                extrinsic_matrix=extrinsic_matrix,
                intrinsic_matrix=intrinsic_matrix,
                radii=radii[mask],
                sigmas=sigmas[mask],
                image_size_xy=image_size_xy,
                back_projected_home_pos=back_projected_home_pos,
                closest_image_arg=closest_image_arg,
                n_distortion_coefs=n_dist_coef,
                debug_nozzle_and_home_pos=debug_nozzle_and_home_pos,
                residuals=result.fun,
                all_debug_data_to_store = all_debug_data_to_store,
                debug_folder=settings.debug_folder,
            )

    except KeyboardInterrupt:
        print_debug(">>>> Interrupted by user <<<<")
        raise
    except Exception:
        traceback.print_exc()
        raise
