# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Point-cache serialization."""

__all__ = [
    "store_all_points",
    "load_all_points",
]

from pathlib import Path

import csv
import io

import numpy as np

from ..atomic import atomic_write_text


def store_all_points(file: Path,
                     robot_positions: np.ndarray,
                     center_points: np.ndarray,
                     radii: np.ndarray,
                     sigmas: np.ndarray,
                     image_sizes: np.ndarray,
                     directions: np.ndarray) -> None:
    """Store all extracted data."""
    all_data = np.asarray([*robot_positions.T, *center_points.T, radii, sigmas, *image_sizes.T, directions]).T
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(["Xr", "Yr", "Zr", "Xc", "Yc", "radius", "sigma border", "image height", "image width",
                     "nozzle_direction"])
    writer.writerows(all_data)
    atomic_write_text(file, buffer.getvalue())


def load_all_points(file: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load stored all extracted data"""
    with file.open(mode="r", newline="") as f:
        f.readline()
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONNUMERIC)
        all_data = np.asarray([row for row in reader], dtype=np.float64)

    robot_positions = all_data[:, :3]
    center_points = all_data[:, 3:5]
    radii = all_data[:, 5]
    sigmas = all_data[:, 6]
    image_sizes = all_data[:, 7:9]
    directions = all_data[:, 9].astype(np.int8)
    return robot_positions, center_points, radii, sigmas, image_sizes, directions
