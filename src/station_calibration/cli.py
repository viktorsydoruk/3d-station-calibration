#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0
"""Folder calibration workflow and command-line entry point.

The workflow analyzes a folder of sphere images, feeds the observations into the
shared calibration session, and writes the calibration result below the analysis
folder. The heavy lifting lives in the session and numerical pipeline modules.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path
import traceback

import numpy as np

from . import __version__
from .calibration import (
    back_projected_point,
    calculate_calibration_errors,
    print_calibration,
)
from .debug import DebugInfo
from .models import CalibrationObservation, CalibrationResult
from .robot import get_nozzle_end_home_position
from .session import CalibrationSession
from .settings import Settings
from .sources.folder import (
    FolderCalibrationSource,
    observations_to_arrays,
)
from .storage import store_calibration, store_nozzle_uncertainty
from .support import calculate_errors
from .uncertainty import bootstrap_nozzle_home


def _write_nozzle_uncertainty_report(
    settings: Settings,
    result: CalibrationResult,
    fit_observations: Sequence[CalibrationObservation],
    *,
    nozzle_home_position: np.ndarray,
    sphere_home_position: np.ndarray,
    sphere_diameter_mm: float,
) -> Path | None:
    """Run the optional post-fit bootstrap and write its sidecar report."""
    if not settings.uncertainty_enabled:
        return None

    try:
        bootstrap = bootstrap_nozzle_home(
            fit_observations,
            result,
            settings,
            n_bootstrap=settings.uncertainty_n_bootstrap,
            seed=settings.uncertainty_seed,
        )
        metadata = {
            "source": str(settings.main_folder),
            "fit": {
                "observation_count": result.observation_count,
                "observations_used": result.n_used,
                "rmse": None if result.rmse is None else float(result.rmse),
                "n_distortion_coefs": result.n_distortion_coefs,
            },
            "bootstrap_config": {
                "n_bootstrap": settings.uncertainty_n_bootstrap,
                "seed": settings.uncertainty_seed,
            },
            "sphere_home_position": np.asarray(
                sphere_home_position, dtype=np.float64
            ).tolist(),
            "sphere_diameter_mm": float(sphere_diameter_mm),
            "nozzle_home_position": np.asarray(
                nozzle_home_position, dtype=np.float64
            ).tolist(),
        }
        report_path = store_nozzle_uncertainty(
            report=bootstrap.as_dict(),
            output_folder=settings.output_folder,
            filename=settings.uncertainty_report_filename,
            metadata=metadata,
        )
    except Exception as error:
        # The calibration itself is already complete and stored. A failed
        # optional diagnostic must not turn a valid calibration into a failure.
        print(f"Warning: nozzle uncertainty bootstrap failed: {error}")
        return None

    if bootstrap.n_failed:
        print(
            "Warning: "
            f"{bootstrap.n_failed} of {bootstrap.n_requested} nozzle "
            "uncertainty bootstrap replicates failed."
        )
    print(
        "Nozzle uncertainty (1 sigma): "
        f"std = [{', '.join(f'{float(value):.6f}' for value in bootstrap.std)}] mm, "
        f"norm = {bootstrap.norm_std:.6f} mm; report: {report_path}"
    )
    return report_path


def main(folder_to_analyze: str | Path, **opts) -> None:
    settings = Settings(folder_to_analyze, **opts)
    print_debug = DebugInfo(settings.debug)

    print_debug(f"{'':=>100}")
    print_debug(f"{f' Analysis of {settings.main_folder} ':-^100}")
    print_debug(f"{'':=>100}")

    try:
        # Feed the folder observations one at a time into a single session. The
        # session refits every ``fit_every_n`` observations, mirroring the
        # incremental Ice workflow; the guaranteed final fit happens after all
        # images are added.
        source = FolderCalibrationSource(settings, print_debug)
        dataset = source.load()
        session = CalibrationSession(
            settings,
            print_debug,
            fit_every_n=settings.fit_every_n,
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
        mask = np.asarray(result.fit_mask, dtype=bool)
        n_dist_coef = result.n_distortion_coefs

        rel_robot_positions = robot_positions - pos_home
        inlier_robot_positions = rel_robot_positions[mask]
        inlier_center_points = center_points_adjusted[mask]
        inlier_radii = radii[mask]
        inlier_sigmas = sigmas[mask]
        inlier_directions = all_directions[mask]

        # Calculating the nozzle home position. Outliers removed by the fit must
        # not influence the sphere diameter or its lateral offset.
        nozzle_end_home_pos, sphere_diam_mm, debug_nozzle_and_home_pos = (
            get_nozzle_end_home_position(
                sphere_home_position=pos_home,
                robot_positions=inlier_robot_positions,
                image_center_points=inlier_center_points,
                intrinsic_matrix=intrinsic_matrix,
                extrinsic_matrix=extrinsic_matrix,
                distortion=distortion,
                sigmas=inlier_sigmas,
                radii=inlier_radii,
                all_directions=inlier_directions,
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
            n_distortion_coefs=n_dist_coef,
            rmse=result.rmse,
            observation_count=result.observation_count,
            observations_used=result.n_used,
            sphere_home_position=pos_home,
        )

        _write_nozzle_uncertainty_report(
            settings,
            result,
            fit_observations,
            nozzle_home_position=nozzle_end_home_pos,
            sphere_home_position=pos_home,
            sphere_diameter_mm=sphere_diam_mm,
        )

        if settings.debug:
            from .plots import visualize_results

            print_debug(f"Sphere center home position: {pos_home}, estimated sphere diameter: {sphere_diam_mm: 0.3f} mm")
            print_debug(f"Nozzle center home position: {nozzle_end_home_pos}")

            closest_image_arg = int(np.argmin(np.sqrt(np.sum((inlier_robot_positions-nozzle_end_home_pos[None, :])**2, axis=1))))

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
                rel_robot_positions=inlier_robot_positions,
                center_points_adjusted=inlier_center_points,
                extrinsic_matrix=extrinsic_matrix,
                intrinsic_matrix=intrinsic_matrix,
                radii=inlier_radii,
                sigmas=inlier_sigmas,
                image_size_xy=image_size_xy,
                back_projected_home_pos=back_projected_home_pos,
                closest_image_arg=closest_image_arg,
                n_distortion_coefs=n_dist_coef,
                debug_nozzle_and_home_pos=debug_nozzle_and_home_pos,
                residuals=getattr(
                    optimize_result,
                    "raw_fun",
                    optimize_result.fun,
                ),
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
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
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
    parser.add_argument(
        "--subpixel-edges",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="refine sphere edges to the sub-pixel 50 %% intensity crossing",
    )
    parser.add_argument("--target-observations", type=int, default=None)
    parser.add_argument("--max-observations", type=int, default=None)
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        default=None,
        help="write the optional post-fit nozzle-uncertainty bootstrap report",
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_false",
        default=None,
        dest="bootstrap",
        help="disable the bootstrap report even when the config enables it",
    )
    parser.add_argument(
        "--bootstrap-n",
        type=int,
        default=None,
        help="bootstrap replicates; implies --bootstrap when no explicit toggle is given",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=None,
        help="bootstrap random seed; implies --bootstrap when no explicit toggle is given",
    )

    args = parser.parse_args(argv)
    bootstrap_enabled = args.bootstrap
    if (
        bootstrap_enabled is None
        and (args.bootstrap_n is not None or args.bootstrap_seed is not None)
    ):
        bootstrap_enabled = True
    opts = {
        name: value
        for name, value in {
            "config_file": args.config,
            "debug": args.debug,
            "store_debug_images": args.store_debug_images,
            "load_stored_data": args.load_stored_data,
            "subpixel_edges": args.subpixel_edges,
            "target_observations": args.target_observations,
            "max_observations": args.max_observations,
            "uncertainty_enabled": bootstrap_enabled,
            "uncertainty_n_bootstrap": args.bootstrap_n,
            "uncertainty_seed": args.bootstrap_seed,
        }.items()
        if value is not None
    }
    main(args.folder, **opts)
