#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Report a residual-bootstrap uncertainty for the nozzle home position."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from station_calibration import (
    CalibrationObservation,
    CalibrationResult,
    CalibrationSession,
    FolderDataset,
    ReadinessStatus,
    Settings,
    bootstrap_nozzle_home,
)
from station_calibration.sources.folder import FolderCalibrationSource


def _format_vector(values: np.ndarray) -> str:
    return "[" + ", ".join(f"{float(value): .6f}" for value in values) + "]"


def _format_matrix(matrix: np.ndarray) -> str:
    return "\n".join(
        "  [" + ", ".join(f"{float(value): .6e}" for value in row) + "]"
        for row in matrix
    )


def _load_result(
    settings: Settings,
    dataset: FolderDataset,
    *,
    ready: bool,
) -> tuple[
    CalibrationResult,
    list[CalibrationObservation],
    ReadinessStatus | None,
]:
    session = CalibrationSession(
        settings,
        fit_every_n=settings.fit_every_n if ready else None,
        apply_radius_filter=dataset.apply_radius_filter,
    )
    for observation in dataset.observations:
        session.add_observation(observation)
        if ready and session.is_ready:
            partial_result = session.last_result
            if partial_result is None:
                raise RuntimeError("readiness was reported without a fit result")
            return partial_result, session.fit_observations, session.readiness_status

    if ready:
        raise SystemExit("readiness did not arrive while feeding the observations")

    return session.finish(), session.fit_observations, None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="bootstrap-nozzle",
        description=(
            "Estimate the nozzle-home uncertainty by residual bootstrap. "
            "Robot positions are held fixed."
        ),
    )
    parser.add_argument("folder", type=Path, help="folder containing the calibration data")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=500,
        help="number of bootstrap replicates (default: 500)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--ready",
        action="store_true",
        help="bootstrap the first readiness snapshot instead of all observations",
    )
    parser.add_argument(
        "--load-stored-data",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="reuse an existing all_points.dat cache instead of analyzing images",
    )
    parser.add_argument("--json", type=Path, default=None, help="write the summary as JSON")
    parser.add_argument("--debug", action="store_true", default=False)
    args = parser.parse_args(argv)

    settings = Settings(
        args.folder,
        config_file=args.config,
        load_stored_data=args.load_stored_data,
        debug=args.debug,
    )
    dataset = FolderCalibrationSource(settings).load()
    result, fit_observations, readiness = _load_result(
        settings,
        dataset,
        ready=args.ready,
    )

    bootstrap = bootstrap_nozzle_home(
        fit_observations,
        result,
        settings,
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
    )

    print(f"Folder: {settings.main_folder}")
    print(f"Mode: {'first readiness snapshot' if args.ready else 'all observations'}")
    print(f"Observations: {result.observation_count}, used: {result.n_used}")
    if readiness is not None:
        print(f"Readiness: {readiness.reason.value} - {readiness.detail}")
    print(
        "Bootstrap: "
        f"{bootstrap.n_requested} requested, {bootstrap.n_success} succeeded, "
        f"{bootstrap.n_failed} failed"
    )
    if bootstrap.failure_messages:
        for message in bootstrap.failure_messages:
            print(f"  failure: {message}")

    print(f"Original nozzle [mm]: {_format_vector(bootstrap.original)}")
    print(f"Bootstrap mean  [mm]: {_format_vector(bootstrap.mean)}")
    print(f"Bias            [mm]: {_format_vector(bootstrap.bias)}")
    print("  bias = bootstrap mean - original; it reflects estimator nonlinearity")
    print(f"1 sigma         [mm]: {_format_vector(bootstrap.std)}")
    print(f"1 sigma norm    [mm]: {bootstrap.norm_std:.6f}")
    print(f"Along nozzle    [mm]: {bootstrap.along_std:.6f}")
    print(f"Perpendicular   [mm]: {bootstrap.perpendicular_std:.6f}")
    print(f"1 sigma interval [mm]:\n  lower {_format_vector(bootstrap.lower_1sigma)}\n  upper {_format_vector(bootstrap.upper_1sigma)}")
    print(f"2 sigma interval [mm]:\n  lower {_format_vector(bootstrap.lower_2sigma)}\n  upper {_format_vector(bootstrap.upper_2sigma)}")
    print("Covariance [mm^2]:")
    print(_format_matrix(bootstrap.covariance))

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with args.json.open("w", encoding="utf-8") as handle:
            json.dump(bootstrap.as_dict(), handle, indent=2)
        print(f"JSON written to: {args.json}")


if __name__ == "__main__":
    main()
