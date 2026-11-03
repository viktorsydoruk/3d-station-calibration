# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""On-disk archive for incoming Ice calibration sessions.

Each session gets a timestamped directory below the server's working folder.
The directory is intentionally compatible with the folder workflow: it contains
8-bit TIFF frames and a semicolon-separated ``Calibration3DPositions.csv``. The
latest fit is also written as ``calibration_result.yaml`` so the matrices
returned over Ice remain available later.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from .. import __version__

__all__ = ["SessionArchive"]

CSV_FILENAME = "Calibration3DPositions.csv"
RESULT_FILENAME = "calibration_result.yaml"
METADATA_FILENAME = "session.yaml"


class SessionArchive:
    """Write one Ice session to a timestamped folder.

    The archive is created lazily on the first image. Calling :meth:`close`
    finalizes the metadata and closes the CSV file. A new instance is created
    whenever the Ice servant reinitializes its calibration session.
    """

    def __init__(self,
                 root: str | Path,
                 *,
                 enabled: bool = True,
                 csv_filename: str = CSV_FILENAME) -> None:
        self.root = Path(root).expanduser()
        self.enabled = bool(enabled)
        self.csv_filename = csv_filename
        self._session_dir: Path | None = None
        self._csv_file: Any | None = None
        self._csv_writer: Any | None = None
        self._image_index = 0
        self._started_at: datetime | None = None
        self._last_result_key: tuple[int, int, int] | None = None

    @property
    def session_dir(self) -> Path | None:
        """Return the active session directory, or ``None`` before the first image."""
        return self._session_dir

    @property
    def image_count(self) -> int:
        """Return the number of archived images in the active session."""
        return self._image_index

    def start(self) -> Path | None:
        """Create the session folder and CSV file if they do not exist yet."""
        if not self.enabled:
            return None
        if self._session_dir is not None:
            return self._session_dir

        self.root.mkdir(parents=True, exist_ok=True)
        self._started_at = datetime.now()
        base_name = self._started_at.strftime("%Y%m%d_%H%M")
        session_dir = self.root / base_name
        suffix = 1
        while session_dir.exists():
            session_dir = self.root / f"{base_name}_{suffix:02d}"
            suffix += 1
        session_dir.mkdir(parents=True)

        self._session_dir = session_dir
        self._image_index = 0
        self._last_result_key = None
        csv_path = session_dir / self.csv_filename
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
        return session_dir

    def record(self, image: np.ndarray, robot_position: np.ndarray) -> Path | None:
        """Archive one frame and its robot position.

        Images are converted to 8-bit TIFF and named in the CSV, so the folder
        can be re-analyzed later with ``3dsc <session-folder>``.
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
        if not cv2.imwrite(str(image_path), array):
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

    def write_result(self, result: Any) -> Path | None:
        """Write the latest calibration result if a session has already started."""
        if self._session_dir is None:
            return None

        key = (
            id(result),
            int(getattr(result, "observation_count", -1)),
            int(getattr(result, "n_used", -1)),
        )
        if key == self._last_result_key:
            return None

        data = {
            "session": {
                "started_at": _isoformat(self._started_at),
                "package_version": __version__,
                "image_count": self._image_index,
                "csv_filename": self.csv_filename,
            },
            "camera": {
                "model": "pinhole",
                "resolution": [int(value) for value in result.image_size_xy],
                "intrinsic_matrix": _array_list(result.intrinsic_matrix),
                "extrinsic_matrix": _array_list(result.extrinsic_matrix),
                "distortion_coefficients": _array_list(result.distortion),
                "n_distortion_coefs": int(result.n_distortion_coefs),
                "rmse": _optional_float(result, "rmse"),
                "observation_count": int(
                    getattr(result, "observation_count", 0)
                ),
                "observations_used": int(getattr(result, "n_used", 0)),
                "sphere_home_position": _array_list(
                    getattr(result, "pos_home", [])
                ),
            },
        }
        path = self._session_dir / RESULT_FILENAME
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                data,
                handle,
                sort_keys=False,
                default_flow_style=False,
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
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                data,
                handle,
                sort_keys=False,
                default_flow_style=False,
            )


def _tiff_array(image: np.ndarray) -> np.ndarray:
    """Normalize an incoming frame to an 8-bit TIFF-writable array.

    Frames that are already 8-bit are kept as-is. Wider integer or floating
    point frames are scaled to the full 0-255 range using the frame minimum and
    maximum. This retains visible contrast when the camera uses, for example, a
    12-bit range inside a 16-bit container.
    """
    array = np.asarray(image)
    if array.dtype == np.bool_:
        array = array.astype(np.uint8) * 255
    elif array.dtype != np.uint8:
        array = _to_uint8(array)

    if array.ndim not in (2, 3):
        raise ValueError(f"unsupported archived image shape: {array.shape}")
    if array.ndim == 3 and array.shape[2] not in (1, 3, 4):
        raise ValueError(f"unsupported archived image shape: {array.shape}")
    return np.ascontiguousarray(array)


def _to_uint8(array: np.ndarray) -> np.ndarray:
    """Scale a non-8-bit frame to 8 bits while preserving its contrast."""
    data = array.astype(np.float32)
    if np.isnan(data).any():
        data = np.nan_to_num(data, nan=0.0, posinf=255.0, neginf=0.0)
    low = float(np.min(data))
    high = float(np.max(data))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.zeros(data.shape, dtype=np.uint8)
    scaled = (data - low) * (255.0 / (high - low))
    return np.clip(np.rint(scaled), 0, 255).astype(np.uint8)


def _array_list(value: Any) -> list[Any]:
    return np.asarray(value, dtype=np.float64).tolist()


def _optional_float(value: Any, name: str) -> float | None:
    raw = getattr(value, name, None)
    if raw is None:
        return None
    return float(raw)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone().isoformat(timespec="seconds")
