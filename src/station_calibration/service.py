# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Application service shared by incremental calibration frontends."""

__all__ = ["CalibrationService"]

from collections.abc import Callable

import numpy as np

from .debug import DebugInfo
from .models import CalibrationObservation, CalibrationResult, ObservationRejection
from .readiness import ReadinessStatus
from .session import CalibrationSession
from .settings import Settings
from .stop import StopReason
from .vision import (
    ImageAnalysisResult,
    analyze_image,
    analyze_image_bytes,
    split_image,
)


class CalibrationService:
    """
        Coordinate image analysis and a calibration session.

        This is the seam used by frontends that receive one image at a time. It
        owns the settings-to-analysis mapping and delegates all fit policy,
        readiness, and observation storage to :class:`CalibrationSession`.
    """

    def __init__(self,
                 settings: Settings,
                 print_debug: DebugInfo | None = None,
                 *,
                 session: CalibrationSession | None = None,
                 fit_every_n: int | None = 1,
                 apply_radius_filter: bool = True) -> None:
        self.settings = settings
        self.print_debug = (
            print_debug if print_debug is not None else DebugInfo(settings.debug)
        )
        self.session = (
            session
            if session is not None
            else CalibrationSession(
                settings,
                self.print_debug,
                fit_every_n=fit_every_n,
                apply_radius_filter=apply_radius_filter,
            )
        )
        self._image_index = 0

    def add_observation(self,
                        observation: CalibrationObservation,
                        *,
                        fit: bool | None = None) -> CalibrationResult | None:
        """Add one already analyzed observation."""
        return self.session.add_observation(observation, fit=fit)

    def add_analysis(self,
                     analysis: ImageAnalysisResult,
                     robot_position: np.ndarray,
                     *,
                     source: str | None = None,
                     fit: bool | None = None) -> CalibrationResult | None:
        """Add one analyzed image and its matching robot position."""
        return self.session.add_analysis(
            analysis,
            robot_position,
            source=source,
            fit=fit,
        )

    def add_rejection(self, rejection: ObservationRejection) -> None:
        """Record one rejected image."""
        self.session.add_rejection(rejection)

    def add_image_bytes(self,
                        image_bytes: bytes,
                        robot_position: np.ndarray,
                        *,
                        source: str | None = None,
                        fit: bool | None = None) -> CalibrationResult | None:
        """
            Analyze one encoded image and add it to the calibration session.

            The robot position must already be expressed in the same coordinate
            system as the observations produced by the folder workflow.
        """
        image_index = self._image_index
        self._image_index += 1

        return self._analyze_and_add(
            lambda: analyze_image_bytes(
                image_bytes,
                **self._analysis_kwargs(image_index),
            ),
            robot_position,
            source=source,
            fit=fit,
        )

    def add_image_array(self,
                        image: np.ndarray,
                        robot_position: np.ndarray,
                        *,
                        source: str | None = None,
                        fit: bool | None = None) -> CalibrationResult | None:
        """
            Analyze one raw NumPy image and add it to the calibration session.

            Two-dimensional arrays are interpreted as raw Bayer frames, matching
            the folder workflow. Three-channel arrays are interpreted as BGR.
            The robot position must already be expressed in the same coordinate
            system as the observations produced by the folder workflow.
        """
        image_index = self._image_index
        self._image_index += 1

        def analyze() -> ImageAnalysisResult:
            image_gray, image_color = split_image(image)
            return analyze_image(
                image_gray,
                image_color,
                **self._analysis_kwargs(image_index),
            )

        return self._analyze_and_add(
            analyze,
            robot_position,
            source=source,
            fit=fit,
        )

    def _analyze_and_add(self,
                         analyze: Callable[[], ImageAnalysisResult],
                         robot_position: np.ndarray,
                         *,
                         source: str | None,
                         fit: bool | None) -> CalibrationResult | None:
        """Analyze one frame, converting analysis failures into rejections."""
        try:
            analysis = analyze()
        except Exception as exc:  # noqa: BLE001 - bad frames must not abort the RPC
            reason = f"image analysis failed: {type(exc).__name__}: {exc}"
            self.print_debug(reason)
            self.add_rejection(
                ObservationRejection(reason=reason, source=source)
            )
            return None

        return self.add_analysis(
            analysis,
            robot_position,
            source=source,
            fit=fit,
        )

    def _analysis_kwargs(self, image_index: int) -> dict:
        return {
            "bg_height_px": self.settings.bg_height_pxs,
            "bg_color_est_perc": self.settings.bg_color_est_perc,
            "fixed_bg_threshold": self.settings.fixed_bg_threshold,
            "n_mov_aver": self.settings.n_move_aver,
            "sphere_center_to_nozzle_part": self.settings.sphere_center_to_nozzle_part,
            "min_bg_pixels_on_edges": self.settings.min_bg_pixels_on_edges,
            "blur_est_border_thickness": self.settings.blur_est_border_thickness,
            "subpixel_edges": self.settings.subpixel_edges,
            "print_debug": self.print_debug,
            "image_index": image_index,
            "debug_imagefile": self.settings.debug_folder / f"ice_{image_index:04d}.png",
            "store_debug_images": self.settings.store_debug_images,
        }

    @property
    def is_ready(self) -> bool:
        """Whether the session's fit has saturated."""
        return self.session.is_ready

    @property
    def readiness_status(self) -> ReadinessStatus:
        """Full saturation-based readiness result from the session."""
        return self.session.readiness_status

    @property
    def readiness_reason(self) -> StopReason:
        """Reason for the saturation-based readiness state."""
        return self.session.readiness_reason

    @property
    def readiness_detail(self) -> str | None:
        """Human-readable saturation-based readiness detail."""
        return self.session.readiness_detail

    @property
    def stop_reason(self) -> StopReason:
        """Combined count and saturation readiness reason from the session."""
        return self.session.stop_reason

    @property
    def stop_detail(self) -> str | None:
        """Combined readiness detail from the session."""
        return self.session.stop_detail

    @property
    def count_reason(self) -> StopReason:
        """Count-only stop-policy reason from the session."""
        return self.session.count_reason

    @property
    def count_detail(self) -> str | None:
        """Count-only stop-policy detail from the session."""
        return self.session.count_detail

    @property
    def last_result(self) -> CalibrationResult | None:
        return self.session.last_result

    def request_stop(self, detail: str | None = None) -> None:
        """Request an explicit stop; readiness still requires the count floor."""
        self.session.request_stop(detail)

    def finish(self) -> CalibrationResult:
        """Return the guaranteed final fit, including all new observations."""
        return self.session.finish()

    def finish_if_ready(self) -> CalibrationResult | None:
        """Finish only when the session has reached its stop condition."""
        return self.session.finish_if_ready()
