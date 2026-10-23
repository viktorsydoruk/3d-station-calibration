"""Functions to work with files"""

__all__ = ["load_robot_positions", "search_images", "store_all_points", "load_all_points", "store_calibration"]

from itertools import chain
from pathlib import Path
import csv
import yaml

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


def store_all_points(file: Path,
                     robot_positions: np.ndarray,
                     center_points: np.ndarray,
                     radii: np.ndarray,
                     sigmas: np.ndarray,
                     image_sizes: np.ndarray,
                     directions: np.ndarray) -> None:
    """Store all extracted data"""
    all_data = np.asarray([*robot_positions.T, *center_points.T, radii, sigmas, *image_sizes.T, directions]).T
    with file.open(mode="w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["Xr", "Yr", "Zr", "Xc", "Yc", "radius", "sigma border", "image height", "image width",
                         "nozzle_direction"])
        writer.writerows(all_data)


def load_all_points(file: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load stored all extracted data"""
    with file.open(mode="r", newline="") as f:
        f.readline()
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONNUMERIC)
        all_data = np.asarray([row for row in reader], dtype=np.float32)  # fixme: float64 is not working, why?

    robot_positions = all_data[:, :3]
    center_points = all_data[:, 3:5]
    radii = all_data[:, 5]
    sigmas = all_data[:, 6]
    image_sizes = all_data[:, 7:9]
    directions = all_data[:, 9].astype(np.int8)
    return robot_positions, center_points, radii, sigmas, image_sizes, directions


def store_calibration(nozzle_home_position: np.ndarray,
                      intrinsic_matrix: np.ndarray,
                      extrinsic_matrix: np.ndarray,
                      distortion_coefficients: np.ndarray,
                      intrinsic_std: np.ndarray,
                      rot_vec_std: np.ndarray,
                      tra_vec_std: np.ndarray,
                      distortion_std: np.ndarray,
                      image_xy: tuple[int, int],
                      model: str = "pinhole",
                      output_folder: Path = Path('')) -> None:
    calibration_data = {
        "nozzle": {
            "home_position": nozzle_home_position.tolist(),
        },
        "camera": {
            "model": model,
            "resolution": list(image_xy),
            "intrinsic_matrix": intrinsic_matrix.tolist(),
            "extrinsic_matrix": extrinsic_matrix.tolist(),
            "distortion_coefficients": distortion_coefficients.tolist(),
            "errors": {
                "intrinsic_std": intrinsic_std.tolist(),
                "rot_vec_std": rot_vec_std.tolist(),
                'tra_vec_std': tra_vec_std.tolist(),
                "distortion_std": distortion_std.tolist(),
            }
        }
     }

    with output_folder.joinpath("calibration_data.yaml").open(mode="w", newline="") as f:
        yaml.dump(calibration_data, f, sort_keys=False, default_flow_style=False)


