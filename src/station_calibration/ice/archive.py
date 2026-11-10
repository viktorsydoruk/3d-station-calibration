# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""On-disk archive for incoming Ice calibration sessions.

Each procedure session has a timestamped folder created by the server. The
archive writes directly into that folder's ``data`` directory so it stays
compatible with the folder workflow: TIFF frames at their source bit depth plus
a semicolon-separated ``Calibration3DPositions.csv``. The latest fit is also
written as ``calibration_result.yaml`` so the matrices returned over Ice remain
available later.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from .. import __version__
from ..atomic import atomic_write_text
from ..calibration import radial_scale_profile
from ..storage import calibration_document
from ..support import DEFAULT_REPORT_PRECISION, ReportPrecision

__all__ = ["SessionArchive"]

CSV_FILENAME = "Calibration3DPositions.csv"
RESULT_FILENAME = "calibration_result.yaml"
METADATA_FILENAME = "session.yaml"

# Adobe Deflate is smaller than LZW for noisy 16-bit frames and is understood
# by OpenCV, Pillow, ImageMagick, and the usual scientific TIFF readers.
TIFF_COMPRESSION = cv2.IMWRITE_TIFF_COMPRESSION_ADOBE_DEFLATE

# OpenCV silently falls back to 8-bit for dtypes it cannot encode, so reject
# anything outside the explicitly supported TIFF sample formats.
_TIFF_DTYPES = frozenset({
    np.dtype(np.uint8),
    np.dtype(np.uint16),
    np.dtype(np.int16),
    np.dtype(np.int32),
    np.dtype(np.uint32),
    np.dtype(np.float32),
    np.dtype(np.float64),
})


class SessionArchive:
    """Write one Ice session directly into a prepared data directory.

    The directory is created by :class:`ProcedureRegistry` before ``init``
    returns, so the archive itself does not create a second timestamp folder. The
    archive starts lazily on the first image. Calling :meth:`close` finalizes the
    metadata and closes the CSV file.
    """

    def __init__(self,
                 data_folder: str | Path,
                 *,
                 enabled: bool = True,
                 csv_filename: str = CSV_FILENAME,
                 procedure_id: int | None = None,
                 session_folder: str | Path | None = None,
                 config_file: str | Path | None = None,
                 precision: ReportPrecision = DEFAULT_REPORT_PRECISION) -> None:
        self.data_folder = Path(data_folder).expanduser()
        self.enabled = bool(enabled)
        self.csv_filename = csv_filename
        self.procedure_id = procedure_id
        self.session_folder = (
            Path(session_folder).expanduser()
            if session_folder is not None
            else self.data_folder.parent
        )
        self.config_file = (
            Path(config_file).expanduser() if config_file is not None else None
        )
        self.precision = precision
        self._session_dir: Path | None = None
        self._csv_file: Any | None = None
        self._csv_writer: Any | None = None
        self._image_index = 0
        self._started_at: datetime | None = None
        self._last_result_key: tuple[int, int, int] | None = None

    @property
    def session_dir(self) -> Path | None:
        """Return the active data directory, or ``None`` before the first image."""
        return self._session_dir

    @property
    def image_count(self) -> int:
        """Return the number of archived images in the active session."""
        return self._image_index

    def start(self) -> Path | None:
        """Create the data folder and CSV file if they do not exist yet."""
        if not self.enabled:
            return None
        if self._session_dir is not None:
            return self._session_dir

        self.data_folder.mkdir(parents=True, exist_ok=True)
        self._started_at = datetime.now()

        self._session_dir = self.data_folder
        self._image_index = 0
        self._last_result_key = None
        csv_path = self._session_dir / self.csv_filename
        self._csv_file = csv_path.open("w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(
            self._csv_file,
            delimiter=";",
            lineterminator="\n",
        )
        # A first field containing "calibration" is treated as a comment by
        # the folder workflow's CSV reader.
        self._csv_writer.writerow(
            ["calibration session", "Xr", "Yr", "Zr", "image"]
        )
        self._csv_file.flush()
        self._write_metadata()
        return self._session_dir

    def record(self, image: np.ndarray, robot_position: np.ndarray) -> Path | None:
        """Archive one frame and its robot position.

        Images are written as compressed TIFF at their source bit depth and
        named in the CSV, so the data folder can be re-analyzed later with
        ``3dsc <data-folder>``.
        """
        session_dir = self.start()
        if session_dir is None:
            return None
        if self._csv_writer is None or self._csv_file is None:
            raise RuntimeError("session archive CSV is not initialized")

        self._image_index += 1
        image_name = f"image_{self._image_index:04d}.tif"
        image_path = session_dir / image_name
        array = _tiff_array(image)
        if not cv2.imwrite(
            str(image_path),
            array,
            [cv2.IMWRITE_TIFF_COMPRESSION, TIFF_COMPRESSION],
        ):
            raise OSError(f"could not write archived image: {image_path}")

        position = np.asarray(robot_position, dtype=np.float64).reshape(3)
        self._csv_writer.writerow(
            [
                f"{position[0]:.12g}",
                f"{position[1]:.12g}",
                f"{position[2]:.12g}",
                image_name,
            ]
        )
        self._csv_file.flush()
        return image_path

    def write_result(
        self,
        result: Any,
        *,
        errors: Mapping[str, np.ndarray] | None = None,
    ) -> Path | None:
        """Write the latest calibration result if a session has already started.

        ``errors`` carries the fitted one-sigma arrays (``intrinsic_std``,
        ``rot_vec_std``, ``tra_vec_std``, ``distortion_std``) so the archived
        document is rounded like the folder workflow's result and exposes the
        same uncertainties.
        """
        if self._session_dir is None:
            return None

        key = (
            id(result),
            int(getattr(result, "observation_count", -1)),
            int(getattr(result, "n_used", -1)),
        )
        if key == self._last_result_key:
            return None

        session_metadata = {
            "procedure_id": self.procedure_id,
            "session_folder": str(self.session_folder),
            "data_folder": str(self.data_folder),
            "config_file": (
                str(self.config_file)
                if self.config_file is not None
                else None
            ),
            "started_at": _isoformat(self._started_at),
            "package_version": __version__,
            "image_count": self._image_index,
            "csv_filename": self.csv_filename,
        }
        rmse_value = getattr(result, "rmse", None)
        radial_scale = None
        adjusted_centers = getattr(result, "center_points_adjusted", None)
        fit_mask = getattr(result, "fit_mask", None)
        if adjusted_centers is not None and fit_mask is not None:
            centers = np.asarray(adjusted_centers, dtype=np.float64)
            mask = np.asarray(fit_mask, dtype=bool)
            if centers.shape[:1] == mask.shape:
                radial_scale = radial_scale_profile(
                    centers[mask],
                    result.intrinsic_matrix,
                    result.distortion,
                )
        data = calibration_document(
            nozzle_home_position=None,
            intrinsic_matrix=result.intrinsic_matrix,
            extrinsic_matrix=result.extrinsic_matrix,
            distortion_coefficients=result.distortion,
            image_xy=result.image_size_xy,
            n_distortion_coefs=int(result.n_distortion_coefs),
            rmse=None if rmse_value is None else float(rmse_value),
            observation_count=int(getattr(result, "observation_count", 0)),
            observations_used=int(getattr(result, "n_used", 0)),
            sphere_home_position=getattr(result, "pos_home", None),
            radial_scale=radial_scale,
            errors=errors,
            session=session_metadata,
            precision=self.precision,
        )
        path = self._session_dir / RESULT_FILENAME
        atomic_write_text(
            path,
            yaml.safe_dump(
                data,
                sort_keys=False,
                default_flow_style=False,
            ),
        )
        self._last_result_key = key
        return path

    def close(self) -> None:
        """Finalize the session metadata and close the CSV file."""
        if self._session_dir is not None:
            self._write_metadata(ended=True)
        if self._csv_file is not None:
            self._csv_file.close()
        self._csv_file = None
        self._csv_writer = None

    def _write_metadata(self, *, ended: bool = False) -> None:
        if self._session_dir is None:
            return
        data = {
            "session": {
                "procedure_id": self.procedure_id,
                "session_folder": str(self.session_folder),
                "data_folder": str(self.data_folder),
                "config_file": (
                    str(self.config_file)
                    if self.config_file is not None
                    else None
                ),
                "started_at": _isoformat(self._started_at),
                "ended_at": (
                    datetime.now().astimezone().isoformat(timespec="seconds")
                    if ended
                    else None
                ),
                "package_version": __version__,
                "image_count": self._image_index,
                "csv_filename": self.csv_filename,
                "source": "ice",
            }
        }
        path = self._session_dir / METADATA_FILENAME
        atomic_write_text(
            path,
            yaml.safe_dump(
                data,
                sort_keys=False,
                default_flow_style=False,
            ),
        )


def _tiff_array(image: np.ndarray) -> np.ndarray:
    """Return a TIFF-writable array without discarding the source precision.

    Integer and floating-point frames keep their original dtype and bit depth.
    Boolean frames are stored as uint8 because TIFF has no boolean sample type.
    """
    array = np.asarray(image)
    if array.dtype == np.bool_:
        array = array.astype(np.uint8) * 255
    elif array.dtype not in _TIFF_DTYPES:
        raise TypeError(f"unsupported archived image dtype: {array.dtype}")

    if array.ndim not in (2, 3):
        raise ValueError(f"unsupported archived image shape: {array.shape}")
    if array.ndim == 3 and array.shape[2] not in (1, 3, 4):
        raise ValueError(f"unsupported archived image shape: {array.shape}")
    return np.ascontiguousarray(array)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone().isoformat(timespec="seconds")
