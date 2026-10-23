# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Calibration-result serialization."""

__all__ = [
    "store_calibration",
]

from pathlib import Path

import numpy as np
import yaml


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
