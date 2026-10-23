# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Robot-position and image-file discovery."""

__all__ = [
    "load_robot_positions",
    "search_images",
]

from itertools import chain
from pathlib import Path

import csv
import numpy as np


def load_robot_positions(file: Path) -> tuple[np.ndarray, list[str]]:
    """
        Load robot positions from a file

    :param file: path to file
    :return: numpy array of robot positions (Nx3)
    """
    if not file.exists():
        raise FileNotFoundError(f"File {file} does not exist")

    # robot_points = np.loadtxt(
    #     file,
    #     delimiter=";",
    #     dtype=float
    # )
    robot_points = np.empty((0, 3), dtype=float)
    image_names = []
    with file.open(mode="r", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if "calibration" in row[0]:  # adaptation to the new version of the file, where info line is presented
                continue
            robot_points = np.append(robot_points, [list(map(float, row[:3]))], axis=0)
            if len(row) > 3:
                image_names.append(row[3])

    return robot_points, image_names


def search_images(image_folder: Path,
                  image_names: list[str],
                  patterns: tuple[str, ...] = ("*.tif", "*.tiff"),
                  sort_by_mtime: bool = True) -> list[Path]:
    """
        Search all image files matching patterns
    :param image_folder: folder containing image files
    :param image_names: names of image files if stored in the file with position of the robotic arm
    :param patterns: patterns to search for
    :param sort_by_mtime: whether to sort by modified time should be done
    :return: list of image files paths
    """
    if len(image_names) == 0:
        filename_generators = [image_folder.glob(pattern) for pattern in patterns]
        all_filenames = list(chain.from_iterable(filename_generators))

        if sort_by_mtime:
            all_filenames_sorted = sorted(
                all_filenames,
                key=lambda x: x.stat().st_mtime
            )
            return all_filenames_sorted
    else:
        all_filenames = [image_folder / image_name for image_name in image_names]

    return all_filenames
