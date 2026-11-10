# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Calibration-result serialization."""

__all__ = [
    "RESULT_SCHEMA_VERSION",
    "NOZZLE_UNCERTAINTY_SCHEMA_VERSION",
    "NOZZLE_HOME_DECIMALS",
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
from ..support import reported, reported_error


RESULT_SCHEMA_VERSION = 1
NOZZLE_UNCERTAINTY_SCHEMA_VERSION = 1

#: The nozzle home position is reported in millimetres with micrometre resolution.
NOZZLE_HOME_DECIMALS = 3


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
    radial_scale: Mapping[str, Any] | None = None,
    session: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shared YAML/JSON-compatible calibration result document.

    Values with a one-sigma estimate are rounded to
    :data:`~station_calibration.support.ERROR_SIGNIFICANT_DIGITS` significant
    digits of that uncertainty. The nozzle home position keeps micrometre
    resolution, and values without an uncertainty are written with their full
    float precision.
    """
    uncertainties: Mapping[str, Any] = {} if errors is None else errors

    intrinsic_values, intrinsic_errors = _paired_values(
        intrinsic_matrix, uncertainties.get("intrinsic_std")
    )
    distortion_values, distortion_errors = _paired_values(
        distortion_coefficients, uncertainties.get("distortion_std")
    )
    extrinsic_array = np.asarray(extrinsic_matrix, dtype=np.float64)
    translation_values, translation_errors = _paired_values(
        extrinsic_array[:3, 3], uncertainties.get("tra_vec_std")
    )
    # Rotation and translation share one homogeneous matrix, but the fitted
    # one-sigma values describe the rotation vector, not the rotation-matrix
    # entries, so only the translation column is rounded here.
    extrinsic_values = _array_list(extrinsic_array)
    for row, translation in enumerate(translation_values):
        extrinsic_values[row][3] = translation

    camera_errors: dict[str, Any] | None = None
    if errors is not None:
        rounded_errors = {
            "intrinsic_std": intrinsic_errors,
            "rot_vec_std": _error_list(uncertainties.get("rot_vec_std")),
            "tra_vec_std": translation_errors,
            "distortion_std": distortion_errors,
        }
        camera_errors = {
            name: rounded_errors.get(name, _array_list(value))
            for name, value in uncertainties.items()
        }

    camera: dict[str, Any] = {
        "model": model,
        "resolution": [int(value) for value in image_xy],
        "intrinsic_matrix": intrinsic_values,
        "extrinsic_matrix": extrinsic_values,
        "distortion_coefficients": distortion_values,
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
        "errors": camera_errors,
        "radial_scale": (
            None
            if radial_scale is None
            else {
                name: _array_list(value)
                for name, value in radial_scale.items()
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
            else _decimals_list(nozzle_home_position, NOZZLE_HOME_DECIMALS)
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
                      sphere_home_position: np.ndarray | None = None,
                      radial_scale: Mapping[str, Any] | None = None) -> None:
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
        radial_scale=radial_scale,
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


def _paired_values(
    values: np.ndarray,
    errors: np.ndarray | None,
) -> tuple[list[Any], list[Any] | None]:
    """Round values and their one-sigma errors to the same decimal place."""
    array = np.asarray(values, dtype=np.float64)
    if errors is None:
        return array.tolist(), None

    error_array = np.asarray(errors, dtype=np.float64)
    if error_array.shape != array.shape:
        raise ValueError(
            f"error array shape {error_array.shape} does not match value shape "
            f"{array.shape}"
        )
    pairs = [
        reported(value, error)
        for value, error in zip(array.ravel(), error_array.ravel())
    ]
    rounded_values = np.array([pair[0] for pair in pairs], dtype=np.float64)
    rounded_errors = np.array([pair[1] for pair in pairs], dtype=np.float64)
    return rounded_values.reshape(array.shape).tolist(), rounded_errors.reshape(
        array.shape
    ).tolist()


def _error_list(errors: np.ndarray | None) -> list[Any] | None:
    """Round a standalone one-sigma array to two significant digits."""
    if errors is None:
        return None
    array = np.asarray(errors, dtype=np.float64)
    rounded = [reported_error(value) for value in array.ravel()]
    return np.array(rounded, dtype=np.float64).reshape(array.shape).tolist()


def _decimals_list(values: np.ndarray, decimals: int) -> list[Any]:
    """Round every entry to a fixed number of decimal places."""
    array = np.asarray(values, dtype=np.float64)
    rounded = []
    for value in array.ravel():
        entry = round(float(value), decimals)
        # Avoid surfacing ``-0.0`` for values that round to zero.
        rounded.append(0.0 if entry == 0.0 else entry)
    return np.array(rounded, dtype=np.float64).reshape(array.shape).tolist()
