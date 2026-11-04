# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""ZeroC Ice adapter for the shared calibration service."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np

from ._generated import ensure_generated_on_path

ensure_generated_on_path()

from Phenoseeder import CalibrationPhenoseederIcing, Point  # noqa: E402
from Phyto.Common import (  # noqa: E402
    EXTRINSICMODEL,
    INTRINSICMODEL,
    extrinsicParams,
    imageData,
    intrinsicParams,
)

from .archive import SessionArchive  # noqa: E402
from .images import array_from_image_data  # noqa: E402
from .procedures import ProcedureRegistry, ProcedureSession  # noqa: E402
from ..calibration import calculate_calibration_errors  # noqa: E402
from ..debug import DebugInfo  # noqa: E402
from ..models import CalibrationResult  # noqa: E402
from ..robot import get_nozzle_end_home_position  # noqa: E402
from ..service import CalibrationService  # noqa: E402
from ..settings import Settings  # noqa: E402
from ..sources.folder import observations_to_arrays  # noqa: E402

__all__ = ["CalibrationIceServant"]

ServiceFactory = Callable[[Settings], Any]


class CalibrationIceServant(CalibrationPhenoseederIcing):
    """
        Serve one incremental calibration procedure over Ice.

        The shared protocol carries only the procedure ID and an optional
        server-side configuration file. The server owns the procedures root:

        * ``<procedures-root>/<procedure-id>/config.toml`` is the default config;
        * ``init`` creates ``<procedures-root>/<procedure-id>/<date>/`` with a
          merged ``config.toml`` and a ``data`` folder;
        * ``init`` returns that date folder so the client can derive
          ``<date>/config.toml`` and ``<date>/data``.

        The adapter is intentionally thin: image analysis, fit policy, readiness,
        and final fitting stay in :class:`CalibrationService`.
    """

    def __init__(self,
                 procedures_root: str | Path,
                 *,
                 service_factory: ServiceFactory | None = None,
                 print_debug: DebugInfo | None = None) -> None:
        self._procedures = ProcedureRegistry(procedures_root)
        self._service_factory = service_factory
        self._print_debug = print_debug
        self._lock = RLock()
        self._service: Any | None = None
        self._settings: Settings | None = None
        self._active_procedure_id: int | None = None
        self._session_has_data = False
        self._nozzle_cache_key: tuple[int, int, int] | None = None
        self._nozzle_cache: np.ndarray | None = None
        self._error_cache_result: Any | None = None
        self._error_cache_value: tuple[np.ndarray, ...] | None = None
        self._archive: SessionArchive | None = None
        self._procedure_session: ProcedureSession | None = None

    @property
    def procedures_root(self) -> Path:
        """Return the deployment-owned procedures root."""
        return self._procedures.root

    @property
    def active_procedure_id(self) -> int | None:
        """Return the active procedure ID, or ``None`` before ``init``."""
        return self._active_procedure_id

    @property
    def procedure_session(self) -> ProcedureSession | None:
        """Return the active procedure session paths, or ``None`` before ``init``."""
        return self._procedure_session

    # ------------------------------------------------------------------
    # Ice operations
    # ------------------------------------------------------------------

    def init(self,
             procedureId: int,
             configurationfilepath: str | None = None,
             current: Any = None) -> str:
        """Start a procedure session and return its absolute date folder."""
        with self._lock:
            return self._initialize(procedureId, configurationfilepath)

    def addData(self,
                robotCoord: Point,
                image: imageData,
                current: Any = None) -> None:
        """Analyze one raw camera frame and add it to the calibration session."""
        with self._lock:
            service = self._require_service()
            robot_position = np.array(
                [robotCoord.x, robotCoord.y, robotCoord.z],
                dtype=np.float64,
            )
            if not np.all(np.isfinite(robot_position)):
                raise ValueError("robotCoord must contain only finite values")

            image_array = array_from_image_data(image)
            self._session_has_data = True
            if self._archive is not None:
                self._archive.record(image_array, robot_position)

            result = service.add_image_array(
                image_array,
                robot_position,
                source="ice",
            )
            self._remember_result(result)

    def isReady(self, current: Any = None) -> bool:
        """Return the session readiness flag without forcing a final fit."""
        with self._lock:
            if self._service is None:
                return False
            return bool(self._service.is_ready)

    def getIntrinsic(self, current: Any = None) -> tuple[intrinsicParams, list[float]]:
        """Return the 3x3 intrinsic matrix and row-major one-sigma uncertainties."""
        with self._lock:
            result = self._current_result()
            intrinsic = np.asarray(result.intrinsic_matrix, dtype=np.float64).reshape(3, 3)
            return (
                intrinsicParams(
                    modelId=INTRINSICMODEL.INTRINSICMATRIX,
                    modelParams=[float(value) for value in intrinsic.reshape(-1)],
                ),
                self._intrinsic_error_sequence(result),
            )

    def getExtrinsic(self,
                     current: Any = None
                     ) -> tuple[extrinsicParams, list[float]]:
        """Return the rotation matrix, translation, and six uncertainty values.

        ``EXTRINSICROTMATRIX`` stores ``Tx, Ty, Tz`` followed by the row-major
        3x3 rotation, as defined by the shared ``PhytoCommon.ice`` contract.
        """
        with self._lock:
            result = self._current_result()
            _, _, rotation_std, translation_std = self._calibration_errors(result)
            rotation = result.extrinsic_matrix[:3, :3]
            translation = result.extrinsic_matrix[:3, 3]
            error = [
                *[float(value) for value in rotation_std],
                *[float(value) for value in translation_std],
            ]
            return (
                extrinsicParams(
                    modelId=EXTRINSICMODEL.EXTRINSICROTMATRIX,
                    modelParams=[
                        *[float(value) for value in translation],
                        *[float(value) for value in rotation.reshape(-1)],
                    ],
                ),
                error,
            )

    def getDistortion(self, current: Any = None) -> tuple[list[float], list[float]]:
        """Return the active distortion coefficients and their uncertainties."""
        with self._lock:
            result = self._current_result()
            _, distortion_std, _, _ = self._calibration_errors(result)
            n_coefficients = int(result.n_distortion_coefs)
            distortion = [
                float(value)
                for value in result.distortion[:n_coefficients]
            ]
            error = [
                float(value)
                for value in distortion_std[:n_coefficients]
            ]
            return distortion, error

    def getOptimalNozzlePosition(self, current: Any = None) -> Point:
        """Estimate the nozzle-end home position from the current fit."""
        with self._lock:
            result = self._current_result()
            service = self._require_service()
            cache_key = (
                id(result),
                int(result.observation_count),
                int(result.n_used),
            )
            if self._nozzle_cache_key != cache_key or self._nozzle_cache is None:
                self._nozzle_cache = self._estimate_nozzle_position(service, result)
                self._nozzle_cache_key = cache_key

            nozzle = self._nozzle_cache
            return Point(
                x=float(nozzle[0]),
                y=float(nozzle[1]),
                z=float(nozzle[2]),
            )

    def calibrate(self, *args: Any, **kwargs: Any) -> list[float]:
        """Legacy operation retained by the contract; no result is produced."""
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _initialize(self,
                    procedure_id: int,
                    configurationfilepath: str | None) -> str:
        self._guard_procedure_switch(procedure_id)

        profile = self._procedures.create_session(
            procedure_id,
            configurationfilepath,
        )
        settings = Settings(
            profile.data_dir,
            config_file=profile.config_file,
            load_stored_data=False,
        )
        if self._service_factory is None:
            service = CalibrationService(
                settings,
                print_debug=self._print_debug or DebugInfo(settings.debug),
                fit_every_n=1,
                apply_radius_filter=True,
            )
        else:
            service = self._service_factory(settings)

        archive = (
            SessionArchive(
                profile.data_dir,
                csv_filename=settings.robot_pos_file.name,
                procedure_id=procedure_id,
                session_folder=profile.session_dir,
                config_file=profile.config_file,
            )
            if settings.archive_sessions
            else None
        )
        if self._archive is not None:
            self._archive.close()

        self._settings = settings
        self._service = service
        self._archive = archive
        self._active_procedure_id = procedure_id
        self._procedure_session = profile
        self._session_has_data = False
        self._nozzle_cache_key = None
        self._nozzle_cache = None
        self._error_cache_result = None
        self._error_cache_value = None
        return str(profile.session_dir)

    def _guard_procedure_switch(self, procedure_id: int) -> None:
        """Reject switching away from a procedure with an unfinished session."""
        if self._active_procedure_id is None:
            return
        if procedure_id == self._active_procedure_id:
            return
        if self._service is None or not self._session_has_data:
            return
        if self._service.is_ready:
            return

        raise RuntimeError(
            f"procedure {self._active_procedure_id!r} has an active "
            f"calibration; finish it before selecting {procedure_id!r}"
        )

    def close(self) -> None:
        """Finalize the active session archive and close its CSV file."""
        with self._lock:
            if self._archive is not None:
                self._archive.close()

    def _remember_result(self, result: Any | None) -> None:
        if result is not None and self._archive is not None:
            self._archive.write_result(result)

    def _require_service(self) -> Any:
        if self._service is None:
            raise RuntimeError(
                "Calibration service is not initialized; call init first"
            )
        return self._service

    def _require_settings(self) -> Settings:
        if self._settings is None:
            raise RuntimeError(
                "Calibration settings are not initialized; call init first"
            )
        return self._settings

    def _current_result(self) -> CalibrationResult:
        service = self._require_service()
        if service.is_ready:
            result = service.finish_if_ready()
            if result is not None:
                self._remember_result(result)
                return result

        result = service.last_result
        if result is None:
            raise RuntimeError(
                "Calibration is not ready and no fitted result is available"
            )
        self._remember_result(result)
        return result

    def _calibration_errors(
        self,
        result: CalibrationResult,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if self._error_cache_result is result and self._error_cache_value is not None:
            return self._error_cache_value

        settings = self._require_settings()
        value = calculate_calibration_errors(
            result.optimize_result,
            fix_cx_cy=settings.fix_cx_cy,
            n_distortion_coefs=result.n_distortion_coefs,
        )
        self._error_cache_result = result
        self._error_cache_value = value
        return value

    def _intrinsic_error_sequence(self, result: CalibrationResult) -> list[float]:
        """Return one-sigma uncertainties for the 3x3 intrinsic matrix, row-major."""
        intrinsic_std, _, _, _ = self._calibration_errors(result)
        error = np.zeros((3, 3), dtype=np.float64)
        error[0, 0] = intrinsic_std[0, 0]
        error[1, 1] = intrinsic_std[1, 1]
        if not self._require_settings().fix_cx_cy:
            error[0, 2] = intrinsic_std[0, 2]
            error[1, 2] = intrinsic_std[1, 2]
        return [float(value) for value in error.reshape(-1)]

    def _estimate_nozzle_position(
        self,
        service: Any,
        result: CalibrationResult,
    ) -> np.ndarray:
        fit_observations = service.session.fit_observations
        if not fit_observations:
            raise RuntimeError("No fit observations are available")

        (
            robot_positions,
            _center_points,
            radii,
            sigmas,
            directions,
        ) = observations_to_arrays(fit_observations)
        relative_robot_positions = robot_positions - result.pos_home

        nozzle_position, _, _ = get_nozzle_end_home_position(
            sphere_home_position=result.pos_home,
            robot_positions=relative_robot_positions,
            image_center_points=result.center_points_adjusted,
            intrinsic_matrix=result.intrinsic_matrix,
            extrinsic_matrix=result.extrinsic_matrix,
            distortion=result.distortion,
            sigmas=sigmas,
            radii=radii,
            all_directions=directions,
        )
        return np.asarray(nozzle_position, dtype=np.float64)
