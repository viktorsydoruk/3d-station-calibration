# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Calibration-result serialization."""

__all__ = [
    "RESULT_SCHEMA_VERSION",
    "NOZZLE_UNCERTAINTY_SCHEMA_VERSION",
    "calibration_document",
    "store_calibration",
    "store_nozzle_uncertainty",
]

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..atomic import atomic_write_text


RESULT_SCHEMA_VERSION = 1
NOZZLE_UNCERTAINTY_SCHEMA_VERSION = 1


def calibration_document(
    *,
    nozzle_home_position: np.ndarray | None,
    intrinsic_matrix: np.ndarray,
    extrinsic_matrix: np.ndarray,
    distortion_coefficients: np.ndarray,
    image_xy: tuple[int, int],
    model: str = "pinhole",
    n_distortion_coefs: int | None = None,
    rmse: float | None = None,
    observation_count: int | None = None,
    observations_used: int | None = None,
    sphere_home_position: np.ndarray | None = None,
    errors: Mapping[str, np.ndarray] | None = None,
    session: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shared YAML/JSON-compatible calibration result document."""
    camera: dict[str, Any] = {
        "model": model,
        "resolution": [int(value) for value in image_xy],
        "intrinsic_matrix": _array_list(intrinsic_matrix),
        "extrinsic_matrix": _array_list(extrinsic_matrix),
        "distortion_coefficients": _array_list(distortion_coefficients),
        "n_distortion_coefs": (
            None if n_distortion_coefs is None else int(n_distortion_coefs)
        ),
        "rmse": None if rmse is None else float(rmse),
        "observation_count": (
            None if observation_count is None else int(observation_count)
        ),
        "observations_used": (
            None if observations_used is None else int(observations_used)
        ),
        "sphere_home_position": (
            None
            if sphere_home_position is None
            else _array_list(sphere_home_position)
        ),
        "errors": (
            None
            if errors is None
            else {
                name: _array_list(value)
                for name, value in errors.items()
            }
        ),
    }

    document: dict[str, Any] = {"schema_version": RESULT_SCHEMA_VERSION}
    if session is not None:
        document["session"] = dict(session)
    document["nozzle"] = {
        "home_position": (
            None
            if nozzle_home_position is None
            else _array_list(nozzle_home_position)
        ),
    }
    document["camera"] = camera
    return document


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
                      output_folder: Path = Path(''),
                      *,
                      n_distortion_coefs: int | None = None,
                      rmse: float | None = None,
                      observation_count: int | None = None,
                      observations_used: int | None = None,
                      sphere_home_position: np.ndarray | None = None) -> None:
    """Write the folder-workflow calibration result as YAML."""
    document = calibration_document(
        nozzle_home_position=nozzle_home_position,
        intrinsic_matrix=intrinsic_matrix,
        extrinsic_matrix=extrinsic_matrix,
        distortion_coefficients=distortion_coefficients,
        image_xy=image_xy,
        model=model,
        n_distortion_coefs=n_distortion_coefs,
        rmse=rmse,
        observation_count=observation_count,
        observations_used=observations_used,
        sphere_home_position=sphere_home_position,
        errors={
            "intrinsic_std": intrinsic_std,
            "rot_vec_std": rot_vec_std,
            "tra_vec_std": tra_vec_std,
            "distortion_std": distortion_std,
        },
    )
    text = yaml.safe_dump(
        document,
        sort_keys=False,
        default_flow_style=False,
    )
    atomic_write_text(Path(output_folder) / "calibration_data.yaml", text)


def store_nozzle_uncertainty(
    *,
    report: Mapping[str, Any],
    output_folder: str | Path,
    filename: str | Path = "nozzle_uncertainty.json",
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Write the optional nozzle-home bootstrap report as a sidecar JSON file."""
    document: dict[str, Any] = {
        "schema_version": NOZZLE_UNCERTAINTY_SCHEMA_VERSION,
        "diagnostic": "nozzle_home_residual_bootstrap",
    }
    if metadata is not None:
        document.update(metadata)
    document.update(report)

    target = Path(output_folder) / Path(filename)
    atomic_write_text(target, json.dumps(document, indent=2) + "\n")
    return target


def _array_list(value: np.ndarray) -> list[Any]:
    return np.asarray(value, dtype=np.float64).tolist()
