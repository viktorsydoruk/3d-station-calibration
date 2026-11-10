#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Compare background-threshold methods on the real calibration folders.

This is a manual regression check for the image-analysis background estimate,
not part of the automatic test suite because it needs the laboratory data set.
It samples frames from the accepted dark-background folders and reports, per
method, the success rate, the chosen threshold, the radius stability, and the
differences against the percentile method.

Examples::

    uv run python scripts/background_regression.py
    uv run python scripts/background_regression.py --samples 60
    uv run python scripts/background_regression.py --dataset accuracy_test_x --csv bg.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from station_calibration import DebugInfo
from station_calibration.storage import load_robot_positions, search_images
from station_calibration.vision import ImageAnalysisResult, analyze_image, load_image
from station_calibration.vision.detection import (
    estimate_direction,
    get_bg_noise_threshold,
    get_bg_value,
)

DEFAULT_DATA_ROOT = Path(r"P:\3Dcalibration")
METHODS = ("percentile", "mad", "fixed30")
FIXED_THRESHOLD = 30.0


@dataclass(frozen=True)
class DatasetCase:
    """One calibration folder and the robot-position file used with it."""

    name: str
    positions_file: str


DEFAULT_CASES = (
    DatasetCase("accuracy_test_x", "Accuracy3DPositions.csv"),
    DatasetCase("accuracy_test_z", "Accuracy3DPositions.csv"),
    DatasetCase("3D_small_20260929_ceramic", "Calibration3DPositions.csv"),
    DatasetCase("3D_small_20260929_POM", "Calibration3DPositions.csv"),
    DatasetCase("3D_small20260914random_2", "Calibration3DPositions.csv"),
    DatasetCase("3D_small20260914random_3", "Calibration3DPositions.csv"),
    DatasetCase("3D_20260831", "Calibration3DPositions.csv"),
)


@dataclass(frozen=True)
class ResultRow:
    """One analyzed frame for one threshold method."""

    dataset: str
    image: str
    method: str
    direction: int
    threshold: float
    ok: bool
    reason: str
    x: float
    y: float
    radius: float
    sigma: float
    robot_x: float
    robot_y: float
    robot_z: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help=f"folder containing the calibration datasets (default: {DEFAULT_DATA_ROOT})",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=None,
        help="dataset folder to check; repeat the option to select several (default: all)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=30,
        help="number of evenly spaced frames per dataset (default: 30)",
    )
    parser.add_argument("--csv", type=Path, default=None, help="optional CSV output path")
    parser.add_argument("--bg-height-px", type=int, default=200)
    parser.add_argument("--bg-color-est-perc", type=float, default=99.999)
    parser.add_argument("--bg-noise-sigma", type=float, default=5.0)
    parser.add_argument("--n-mov-aver", type=int, default=11)
    parser.add_argument("--sphere-center-to-nozzle-part", type=float, default=0.7)
    parser.add_argument("--min-bg-pixels-on-edges", type=int, default=5)
    parser.add_argument("--blur-est-border-thickness", type=int, default=2)
    parser.add_argument("--subpixel-edges", action="store_true")

    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("--samples must be positive")
    if args.bg_height_px < 2:
        parser.error("--bg-height-px must be at least 2")
    return args


def _select_cases(args: argparse.Namespace) -> list[DatasetCase]:
    if not args.dataset:
        return list(DEFAULT_CASES)

    by_name = {case.name: case for case in DEFAULT_CASES}
    missing = [name for name in args.dataset if name not in by_name]
    if missing:
        raise ValueError(
            "unknown dataset(s): " + ", ".join(missing) + "; choose from: "
            + ", ".join(case.name for case in DEFAULT_CASES)
        )
    return [by_name[name] for name in args.dataset]


def _sample_indices(count: int, samples: int) -> np.ndarray:
    if samples >= count:
        return np.arange(count)
    return np.unique(np.linspace(0, count - 1, samples, dtype=int))


def _threshold_for(
    image_gray: np.ndarray,
    direction: int,
    method: str,
    args: argparse.Namespace,
) -> float:
    if method == "fixed30":
        return FIXED_THRESHOLD
    if direction == 0:
        return float("nan")
    if method == "mad":
        return get_bg_noise_threshold(
            image_gray,
            bg_height_px=args.bg_height_px,
            direction=direction,
            n_sigma=args.bg_noise_sigma,
            percentile_floor=args.bg_color_est_perc,
        )
    return get_bg_value(
        image_gray,
        bg_height_px=args.bg_height_px,
        perc=args.bg_color_est_perc,
        direction=direction,
    )


def _analyze_frame(
    image_gray: np.ndarray,
    method: str,
    args: argparse.Namespace,
) -> ImageAnalysisResult:
    return analyze_image(
        image_gray,
        bg_height_px=args.bg_height_px,
        bg_color_est_perc=args.bg_color_est_perc,
        bg_threshold_method="percentile" if method == "fixed30" else method,
        bg_noise_sigma=args.bg_noise_sigma,
        fixed_bg_threshold=FIXED_THRESHOLD if method == "fixed30" else 0.0,
        n_mov_aver=args.n_mov_aver,
        sphere_center_to_nozzle_part=args.sphere_center_to_nozzle_part,
        min_bg_pixels_on_edges=args.min_bg_pixels_on_edges,
        blur_est_border_thickness=args.blur_est_border_thickness,
        print_debug=DebugInfo(False),
        subpixel_edges=args.subpixel_edges,
    )


def _analyze_dataset(
    case: DatasetCase,
    args: argparse.Namespace,
) -> list[ResultRow]:
    folder = args.data_root / case.name
    positions_path = folder / case.positions_file
    if not folder.is_dir() or not positions_path.is_file():
        print(f"skip {case.name}: missing {positions_path}", file=sys.stderr)
        return []

    robot_positions, image_names = load_robot_positions(positions_path)
    image_paths = search_images(folder, image_names)
    if len(robot_positions) != len(image_paths):
        print(
            f"skip {case.name}: {len(robot_positions)} robot positions vs "
            f"{len(image_paths)} images",
            file=sys.stderr,
        )
        return []

    indices = _sample_indices(len(image_paths), args.samples)
    print(f"{case.name}: {indices.size}/{len(image_paths)} frames")

    rows: list[ResultRow] = []
    for index in indices:
        try:
            image_gray, _ = load_image(image_paths[index])
        except Exception as exc:
            print(
                f"  skip {image_paths[index].name}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            continue
        direction = estimate_direction(image_gray, bg_height_px=args.bg_height_px // 2)
        robot_x, robot_y, robot_z = (float(value) for value in robot_positions[index])

        for method in METHODS:
            threshold = _threshold_for(image_gray, direction, method, args)
            result = _analyze_frame(image_gray, method, args)
            observation = result.observation
            rows.append(
                ResultRow(
                    dataset=case.name,
                    image=image_paths[index].name,
                    method=method,
                    direction=int(direction),
                    threshold=float(threshold),
                    ok=observation is not None,
                    reason=result.reason or "",
                    x=float(observation.x) if observation is not None else float("nan"),
                    y=float(observation.y) if observation is not None else float("nan"),
                    radius=float(observation.radius) if observation is not None else float("nan"),
                    sigma=float(observation.sigma) if observation is not None else float("nan"),
                    robot_x=robot_x,
                    robot_y=robot_y,
                    robot_z=robot_z,
                )
            )
    return rows


def _median_iqr(values: list[float]) -> str:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if finite.size == 0:
        return "n/a"
    median = float(np.median(finite))
    q25, q75 = np.percentile(finite, [25.0, 75.0])
    return f"{median:0.3f} (IQR {q75 - q25:0.3f})"


def _print_summary(rows: list[ResultRow]) -> None:
    grouped: dict[str, dict[str, list[ResultRow]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.dataset][row.method].append(row)

    for dataset, by_method in grouped.items():
        print(f"\n== {dataset} ==")
        for method in METHODS:
            method_rows = by_method.get(method, [])
            if not method_rows:
                continue
            successes = [row for row in method_rows if row.ok]
            print(
                f"  {method:<10} {len(successes):>3}/{len(method_rows):<3}  "
                f"thr={_median_iqr([row.threshold for row in method_rows])}  "
                f"radius={_median_iqr([row.radius for row in successes])}  "
                f"sigma={_median_iqr([row.sigma for row in successes])}"
            )


def _paired_differences(rows: list[ResultRow]) -> None:
    grouped: dict[str, dict[str, list[ResultRow]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.dataset][row.method].append(row)

    print("\nPaired differences against percentile (common successful frames):")
    for dataset, by_method in grouped.items():
        base = {row.image: row for row in by_method.get("percentile", []) if row.ok}
        if not base:
            continue
        print(f"  {dataset}:")
        for method in METHODS:
            if method == "percentile":
                continue
            other = {row.image: row for row in by_method.get(method, []) if row.ok}
            common = sorted(set(base) & set(other))
            if not common:
                print(f"    {method:<10} no common successful frames")
                continue
            dx = np.asarray([other[name].x - base[name].x for name in common])
            dy = np.asarray([other[name].y - base[name].y for name in common])
            dr = np.asarray([other[name].radius - base[name].radius for name in common])
            print(
                f"    {method:<10} n={len(common):<3}  "
                f"|dx|max={np.max(np.abs(dx)):0.3f}  |dy|max={np.max(np.abs(dy)):0.3f}  "
                f"|dr|max={np.max(np.abs(dr)):0.3f}"
            )


def _accuracy_residuals(rows: list[ResultRow]) -> None:
    accuracy_rows = [row for row in rows if row.dataset.startswith("accuracy_")]
    if not accuracy_rows:
        return

    grouped: dict[str, dict[str, list[ResultRow]]] = defaultdict(lambda: defaultdict(list))
    for row in accuracy_rows:
        grouped[row.dataset][row.method].append(row)

    print("\nAccuracy residuals after linear trend removal (pixels):")
    for dataset, by_method in grouped.items():
        base = {row.image: row for row in by_method.get("percentile", []) if row.ok}
        if len(base) < 3:
            continue
        base_rows = [base[name] for name in sorted(base)]
        axes = {
            "robot x": np.asarray([row.robot_x for row in base_rows]),
            "robot y": np.asarray([row.robot_y for row in base_rows]),
            "robot z": np.asarray([row.robot_z for row in base_rows]),
        }
        axis_name, axis_values = max(axes.items(), key=lambda item: float(np.ptp(item[1])))
        if float(np.ptp(axis_values)) == 0.0:
            continue
        print(f"  {dataset} [{axis_name}]:")
        axis_attribute = "robot_" + axis_name.rsplit(" ", 1)[1]
        for method in METHODS:
            other = {row.image: row for row in by_method.get(method, []) if row.ok}
            common = sorted(set(base) & set(other))
            if len(common) < 3:
                print(f"    {method:<10} not enough common successful frames")
                continue
            method_rows = [other[name] for name in common]
            positions = np.asarray(
                [getattr(row, axis_attribute) for row in method_rows],
                dtype=float,
            )
            if float(np.ptp(positions)) == 0.0:
                print(f"    {method:<10} insufficient robot-position range")
                continue
            centers = np.full((len(method_rows), 2), np.nan, dtype=float)
            centers[:, 0] = [row.x for row in method_rows]
            centers[:, 1] = [row.y for row in method_rows]
            residual_norms = []
            for column in range(2):
                coefficients = np.polyfit(positions, centers[:, column], 1)
                residual_norms.append(centers[:, column] - np.polyval(coefficients, positions))
            residuals = np.sqrt(np.sum(np.square(np.asarray(residual_norms)), axis=0))
            print(
                f"    {method:<10} n={len(method_rows):<3}  "
                f"rms={float(np.sqrt(np.mean(np.square(residuals)))):0.3f}  "
                f"max={float(np.max(residuals)):0.3f}"
            )


def _write_csv(path: Path, rows: list[ResultRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> int:
    args = _parse_args()
    try:
        cases = _select_cases(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rows: list[ResultRow] = []
    for case in cases:
        rows.extend(_analyze_dataset(case, args))

    if not rows:
        print("error: no frames were analyzed", file=sys.stderr)
        return 1

    _print_summary(rows)
    _paired_differences(rows)
    _accuracy_residuals(rows)

    if args.csv is not None:
        _write_csv(args.csv, rows)
        print(f"\nCSV written to {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
