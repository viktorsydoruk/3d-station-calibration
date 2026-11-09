# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Point-cache serialization."""

__all__ = [
    "store_all_points",
    "load_all_points",
    "load_all_points_with_covariances",
]

from pathlib import Path

import csv
import io

import numpy as np

from ..atomic import atomic_write_text

_HEADER = [
    "Xr",
    "Yr",
    "Zr",
    "Xc",
    "Yc",
    "radius",
    "sigma border",
    "image height",
    "image width",
    "nozzle_direction",
    "center_cov_xx",
    "center_cov_xy",
    "center_cov_yy",
]


def _covariance_columns(
    center_covariances: np.ndarray | None,
    n_points: int,
) -> np.ndarray:
    """Return (N, 3) centre-covariance columns, using NaN when unavailable."""
    if center_covariances is None:
        return np.full((n_points, 3), np.nan, dtype=np.float64)

    covariance = np.asarray(center_covariances, dtype=np.float64)
    if covariance.shape == (n_points, 2, 2):
        return np.column_stack(
            (
                covariance[:, 0, 0],
                covariance[:, 0, 1],
                covariance[:, 1, 1],
            )
        )
    if covariance.shape == (n_points, 3):
        return covariance
    raise ValueError(
        "center_covariances must have shape "
        f"({n_points}, 2, 2) or ({n_points}, 3), got {covariance.shape}"
    )


def store_all_points(file: Path,
                     robot_positions: np.ndarray,
                     center_points: np.ndarray,
                     radii: np.ndarray,
                     sigmas: np.ndarray,
                     image_sizes: np.ndarray,
                     directions: np.ndarray,
                     center_covariances: np.ndarray | None = None) -> None:
    """Store all extracted data, including optional centre covariances."""
    n_points = len(robot_positions)
    covariance_columns = _covariance_columns(center_covariances, n_points)
    invalid_rows = ~np.isfinite(radii) | ~np.isfinite(sigmas)
    covariance_columns[invalid_rows] = np.nan
    all_data = np.asarray(
        [
            *robot_positions.T,
            *center_points.T,
            radii,
            sigmas,
            *image_sizes.T,
            directions,
            *covariance_columns.T,
        ]
    ).T

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(_HEADER)
    writer.writerows(all_data)
    atomic_write_text(file, buffer.getvalue())


def _read_all_data(file: Path) -> np.ndarray:
    with file.open(mode="r", newline="") as f:
        f.readline()
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONNUMERIC)
        return np.asarray([row for row in reader], dtype=np.float64)


def _unpack_columns(
    all_data: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Unpack the stable first ten columns of a point cache."""
    robot_positions = all_data[:, :3]
    center_points = all_data[:, 3:5]
    radii = all_data[:, 5]
    sigmas = all_data[:, 6]
    image_sizes = all_data[:, 7:9]
    directions = all_data[:, 9].astype(np.int8)
    return robot_positions, center_points, radii, sigmas, image_sizes, directions


def load_all_points(file: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load stored all extracted data (without the optional covariance columns)."""
    return _unpack_columns(_read_all_data(file))


def load_all_points_with_covariances(
    file: Path,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Load the cache including optional per-observation centre covariances.

    The seventh return value has shape ``(N, 2, 2)``.  Caches written before
    covariance support contain only the first ten columns; those covariances are
    returned as ``nan`` so callers can fall back to an unweighted fit.
    """
    all_data = _read_all_data(file)
    unpacked = _unpack_columns(all_data)

    n_points = len(all_data)
    center_covariances = np.full((n_points, 2, 2), np.nan, dtype=np.float64)
    if all_data.ndim == 2 and all_data.shape[1] >= 13:
        center_covariances[:, 0, 0] = all_data[:, 10]
        center_covariances[:, 0, 1] = all_data[:, 11]
        center_covariances[:, 1, 0] = all_data[:, 11]
        center_covariances[:, 1, 1] = all_data[:, 12]

    return (*unpacked, center_covariances)
