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
__version__ = "2026.10.23.1"
__maintainer__ = "Viktor Sydoruk"
__email__ = "v.sydoruk@fz-juelich.de"
__status__ = "Developments"
__date__ = "01.10.2026"


import argparse
from pathlib import Path
import traceback

import numpy as np

from .camera import (
    back_projected_point,
    calculate_calibration_errors,
    print_calibration,
)
from .debug import DebugInfo
from .file import store_calibration
from .plots import visualize_results
from .robot import get_nozzle_end_home_position
from .session import CalibrationSession
from .settings import Settings
from .sources.folder import (
    FolderCalibrationSource,
    observations_to_arrays,
)
from .support import calculate_errors


def main(folder_to_analyze: str | Path, **opts) -> None:
    settings = Settings(folder_to_analyze, **opts)
    print_debug = DebugInfo(settings.debug)

    print_debug(f"{'':=>100}")
    print_debug(f"{f' Analysis of {settings.main_folder} ':-^100}")
    print_debug(f"{'':=>100}")

    try:
        # Feed the folder observations one at a time into a single session. The
        # session refits every ``step_size`` observations, mirroring the incremental
        # Ice workflow; the guaranteed final fit happens after all images are added.
        step_size = 1
        source = FolderCalibrationSource(settings, print_debug)
        dataset = source.load()
        session = CalibrationSession(
            settings,
            print_debug,
            fit_every_n=step_size,
            apply_radius_filter=dataset.apply_radius_filter,
        )
        for rejection in dataset.rejections:
            session.add_rejection(rejection)

        print_debug.debug = False
        all_debug_data_to_store: list[list[str | float| np.floating | np.integer]] = [
            ["N", "N_reduced", "fx", "dfx", "fy", "dfy", "t3", "dt3", "n params", "RMSE"]
        ]
        for observation in dataset.observations:
            partial_result = session.add_observation(observation)
            if partial_result is None:
                continue

            err = calculate_errors(partial_result.optimize_result)
            val = partial_result.optimize_result.x
            print_debug(
                f"{partial_result.observation_count:>3d}. {val[-1]:0.5f} +/- {err[-1]:0.5f}",
                f"RMSE: {partial_result.rmse:0.6f}", len(val),
                f"left: {partial_result.n_used}", print_anyway=True
            )
            all_debug_data_to_store.append(
                [partial_result.observation_count, partial_result.n_used, val[0],
                 err[0], val[1], err[1], val[-1], err[-1], len(val),
                 partial_result.rmse]
            )

        print_debug.debug = settings.debug

        result = session.finish()
        fit_observations = session.fit_observations
        robot_positions, center_points, radii, sigmas, all_directions = (
            observations_to_arrays(fit_observations)
        )
        image_size_xy = result.image_size_xy
        pos_home = result.pos_home
        center_points_adjusted = result.center_points_adjusted
        intrinsic_matrix = result.intrinsic_matrix
        extrinsic_matrix = result.extrinsic_matrix
        distortion = result.distortion
        optimize_result = result.optimize_result
        mask = result.fit_mask
        n_dist_coef = result.n_distortion_coefs

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
            optimize_result,
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
                optimize_result,
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
                residuals=optimize_result.fun,
                all_debug_data_to_store = all_debug_data_to_store,
                debug_folder=settings.debug_folder,
            )

    except KeyboardInterrupt:
        print_debug(">>>> Interrupted by user <<<<")
        raise
    except Exception:
        traceback.print_exc()
        raise


def run_cli(argv: list[str] | None = None) -> None:
    """Run the folder calibration workflow from the command line."""
    parser = argparse.ArgumentParser(
        prog="3dsc",
        description="Calibrate a 3D phenoSeeder station from a folder of images.",
    )
    parser.add_argument("folder", type=Path, help="folder containing the calibration images")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="optional TOML configuration file; defaults to the packaged config",
    )
    parser.add_argument("--debug", action="store_true", default=None)
    parser.add_argument("--store-debug-images", action="store_true", default=None)
    parser.add_argument(
        "--load-stored-data",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="reuse an existing all_points.dat cache instead of analyzing images",
    )
    parser.add_argument("--target-observations", type=int, default=None)
    parser.add_argument("--max-observations", type=int, default=None)

    args = parser.parse_args(argv)
    opts = {
        name: value
        for name, value in {
            "config_file": args.config,
            "debug": args.debug,
            "store_debug_images": args.store_debug_images,
            "load_stored_data": args.load_stored_data,
            "target_observations": args.target_observations,
            "max_observations": args.max_observations,
        }.items()
        if value is not None
    }
    main(args.folder, **opts)
