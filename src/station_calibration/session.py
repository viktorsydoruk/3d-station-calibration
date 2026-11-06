# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Stateful calibration session shared by folder and Ice frontends."""

__all__ = [
    "CalibrationObservation",
    "ObservationRejection",
    "CalibrationResult",
    "CalibrationSession",
    "StopReason",
    "StopPolicy",
    "StopStatus",
]

import numpy as np

from .debug import DebugInfo
from .models import (
    CalibrationObservation,
    CalibrationResult,
    ObservationRejection,
)
from .processes import get_calibration_data
from .settings import Settings
from .stop import StopPolicy, StopReason, StopStatus
from .vision import ImageAnalysisResult, get_radius_outlier_mask


def _validate_fit_output(*,
                         pos_home: np.ndarray,
                         center_points_adjusted: np.ndarray,
                         intrinsic_matrix: np.ndarray,
                         extrinsic_matrix: np.ndarray,
                         distortion: np.ndarray,
                         optimize_result,
                         rmse: float,
                         n_fit_points: int) -> None:
    """Reject non-converged or non-finite numerical results before publication."""
    if not bool(getattr(optimize_result, "success", False)):
        message = getattr(optimize_result, "message", "no convergence information")
        raise ValueError(f"Calibration did not converge: {message}")

    def _finite(name: str, value, shape: tuple[int, ...] | None = None) -> np.ndarray:
        array = np.asarray(value, dtype=np.float64)
        if shape is not None and array.shape != shape:
            raise ValueError(
                f"Calibration returned {name} with shape {array.shape}, expected {shape}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(f"Calibration returned non-finite {name}")
        return array

    _finite("pos_home", pos_home, (3,))
    _finite(
        "center_points_adjusted",
        center_points_adjusted,
        (n_fit_points, 2),
    )
    intrinsic = _finite("intrinsic_matrix", intrinsic_matrix, (3, 3))
    _finite("extrinsic_matrix", extrinsic_matrix, (4, 4))
    _finite("distortion", distortion)

    if intrinsic[0, 0] <= 0 or intrinsic[1, 1] <= 0:
        raise ValueError(
            "Calibration returned a non-positive focal length: "
            f"fx={intrinsic[0, 0]}, fy={intrinsic[1, 1]}"
        )

    rmse_value = float(rmse)
    if not np.isfinite(rmse_value) or rmse_value < 0:
        raise ValueError(f"Calibration returned an invalid RMSE: {rmse_value}")

    params = getattr(optimize_result, "x", None)
    if params is not None:
        _finite("parameter vector", params)
    residuals = getattr(optimize_result, "fun", None)
    if residuals is not None:
        _finite("residual vector", residuals)
    cost = getattr(optimize_result, "cost", None)
    if cost is not None and not np.isfinite(np.asarray(cost, dtype=np.float64)).all():
        raise ValueError(f"Calibration returned a non-finite cost: {cost}")


class CalibrationSession:
    """
        Accumulate observations and refit the camera model as new data arrives.

        The session is source-agnostic: folder and Ice adapters analyze images and
        feed the resulting observations here. By default one fit is performed as
        soon as enough observations survive the radius filter and again after every
        new valid observation. Set ``fit_every_n`` to a larger number to reduce fit
        frequency, or to ``None`` to fit only on an explicit ``fit()``/``finish()``
        call.

        At least ``10 + n_distortion_coefs`` observations are required by default;
        ``min_observations`` can only raise that threshold.

        The session applies the shared radius-outlier filter before fitting. Set
        ``apply_radius_filter=False`` when the source already filtered its data, for
        example when loading a previously stored point cache.

        Readiness is controlled by ``StopPolicy``. By default the session reports
        readiness once 500 valid observations have been collected. Readiness is
        advisory: observations added after that point are still accepted and are
        included in the next fit. The caller decides when to stop sending data
        and then calls :meth:`finish` to publish a result, or aborts the session
        in the frontend. The policy can also set an earlier readiness threshold,
        or the caller can request an explicit stop.
    """

    def __init__(self,
                 settings: Settings,
                 print_debug: DebugInfo | None = None,
                 *,
                 min_observations: int | None = None,
                 fit_every_n: int | None = 1,
                 apply_radius_filter: bool = True,
                 stop_policy: StopPolicy | None = None):
        self.settings = settings
        self.print_debug = print_debug if print_debug is not None else DebugInfo(settings.debug)
        self.apply_radius_filter = bool(apply_radius_filter)

        required_min_observations = 10 + int(settings.n_distortion_coefs)
        if min_observations is None:
            min_observations = required_min_observations
        else:
            min_observations = int(min_observations)
            if min_observations < required_min_observations:
                raise ValueError(
                    "min_observations must be at least "
                    f"{required_min_observations} for the configured distortion model, "
                    f"got {min_observations}"
                )
        if min_observations < 1:
            raise ValueError(f"min_observations must be positive, got {min_observations}")

        if fit_every_n is not None:
            fit_every_n = int(fit_every_n)
            if fit_every_n < 1:
                raise ValueError(f"fit_every_n must be positive or None, got {fit_every_n}")

        self.min_observations = min_observations
        self.fit_every_n = fit_every_n

        if stop_policy is None:
            stop_policy = StopPolicy(
                target_observations=settings.target_observations,
                max_observations=settings.max_observations,
            )
        self.stop_policy = stop_policy

        if (
            self.stop_policy.target_observations is not None
            and self.stop_policy.target_observations < self.min_observations
        ):
            raise ValueError(
                "stop_policy.target_observations must be at least "
                f"min_observations ({self.min_observations}), got "
                f"{self.stop_policy.target_observations}"
            )
        if (
            self.stop_policy.max_observations is not None
            and self.stop_policy.max_observations < self.min_observations
        ):
            raise ValueError(
                "stop_policy.max_observations must be at least "
                f"min_observations ({self.min_observations}), got "
                f"{self.stop_policy.max_observations}"
            )

        self._observations: list[CalibrationObservation] = []
        self._rejections: list[ObservationRejection] = []
        self._last_result: CalibrationResult | None = None
        self._last_fit_error: str | None = None
        self._fit_count = 0
        self._new_since_fit = 0
        self._explicit_stop_detail: str | None = None

    @property
    def observations(self) -> tuple[CalibrationObservation, ...]:
        """All valid observations, in arrival order."""
        return tuple(self._observations)

    @property
    def rejections(self) -> tuple[ObservationRejection, ...]:
        """All rejected analyses, in arrival order."""
        return tuple(self._rejections)

    @property
    def n_observations(self) -> int:
        return len(self._observations)

    @property
    def n_rejections(self) -> int:
        return len(self._rejections)

    @property
    def fit_count(self) -> int:
        return self._fit_count

    @property
    def last_result(self) -> CalibrationResult | None:
        return self._last_result

    @property
    def last_fit_error(self) -> str | None:
        return self._last_fit_error

    @property
    def is_fitted(self) -> bool:
        return self._last_result is not None

    @property
    def can_fit(self) -> bool:
        """Whether enough observations are stored to attempt a fit.

        Radius filtering and calibration outlier detection can still reject points
        during :meth:`fit`.
        """
        return self.n_observations >= self.min_observations

    def _fit_indices(self,
                     radii: np.ndarray | None = None,
                     sigmas: np.ndarray | None = None) -> np.ndarray:
        """Return observation indices that survive the current radius filter."""
        if not self._observations:
            return np.empty(0, dtype=int)
        if not self.apply_radius_filter:
            return np.arange(self.n_observations, dtype=int)

        if radii is None:
            radii = np.array(
                [observation.radius for observation in self._observations],
                dtype=np.float64,
            )
        if sigmas is None:
            sigmas = np.array(
                [observation.sigma for observation in self._observations],
                dtype=np.float64,
            )

        return np.flatnonzero(~get_radius_outlier_mask(radii, sigmas))

    @property
    def can_auto_fit(self) -> bool:
        """Whether an automatic fit has enough observations after radius filtering."""
        return (
            self.can_fit
            and len(self._fit_indices()) >= self.min_observations
        )

    @property
    def new_observations_since_fit(self) -> int:
        return self._new_since_fit

    @property
    def stop_status(self) -> StopStatus:
        """Evaluate the stop policy against the current observation count."""
        return self.stop_policy.evaluate(
            self.n_observations,
            self.min_observations,
            explicit_detail=self._explicit_stop_detail,
        )

    @property
    def is_ready(self) -> bool:
        """Whether no more observations are needed.

        Readiness is based on the stop policy and valid observation count, not on
        whether the latest fit has already run. Call :meth:`finish` or
        :meth:`finish_if_ready` before retrieving calibration results.
        """
        return self.stop_status.ready

    @property
    def stop_reason(self) -> StopReason:
        """Reason for the current readiness state."""
        return self.stop_status.reason

    @property
    def stop_detail(self) -> str | None:
        """Human-readable detail for the current readiness state."""
        return self.stop_status.detail

    @property
    def stop_requested(self) -> bool:
        """Whether an explicit stop has been requested."""
        return self._explicit_stop_detail is not None

    @property
    def image_size_xy(self) -> tuple[int, int] | None:
        """Largest image size seen so far, returned as (width, height)."""
        image_shapes = [observation.image_shape for observation in self._observations]
        image_shapes.extend(
            rejection.image_shape
            for rejection in self._rejections
            if rejection.image_shape is not None
        )
        if not image_shapes:
            return None

        max_height = max(shape[0] for shape in image_shapes)
        max_width = max(shape[1] for shape in image_shapes)
        return max_width, max_height

    @property
    def fit_observations(self) -> tuple[CalibrationObservation, ...]:
        """Observations passed to the last fit after radius filtering."""
        if self._last_result is None:
            return ()
        return tuple(
            self._observations[index]
            for index in self._last_result.fit_observation_indices
        )

    @property
    def used_observations(self) -> tuple[CalibrationObservation, ...]:
        """Observations that survived all filters in the last fit."""
        if self._last_result is None:
            return ()
        return tuple(
            observation
            for observation, used in zip(self._observations, self._last_result.used_mask)
            if used
        )

    def add_rejection(self, rejection: ObservationRejection) -> None:
        """Add one rejected analysis without changing the fit count."""
        if not isinstance(rejection, ObservationRejection):
            raise TypeError("rejection must be an ObservationRejection")
        self._rejections.append(rejection)

    def add_observation(self,
                        observation: CalibrationObservation,
                        *,
                        fit: bool | None = None) -> CalibrationResult | None:
        """
            Add one valid observation.

        :param observation: observation to store
        :param fit: True to fit immediately, False to skip the automatic fit,
                    None to use the session's auto-fit policy
        :return: the new fit result, or None when no fit was performed
        """
        if not isinstance(observation, CalibrationObservation):
            raise TypeError("observation must be a CalibrationObservation")

        self._observations.append(observation)
        self._new_since_fit += 1

        if fit is None:
            fit = (
                self.fit_every_n is not None
                and (
                    self._last_result is None
                    or self._new_since_fit >= self.fit_every_n
                )
                and self.can_auto_fit
            )
        if fit:
            return self.fit()
        return None

    def add_analysis(self,
                     analysis: ImageAnalysisResult,
                     robot_position: np.ndarray,
                     *,
                     source: str | None = None,
                     fit: bool | None = None) -> CalibrationResult | None:
        """
            Add the result of analyzing one image and its matching robot position.

            Rejected analyses are stored separately and do not affect readiness or fit
            counts. Their image size is still considered when determining the camera
            resolution.
        """
        if analysis.observation is None:
            self.add_rejection(
                ObservationRejection(
                    reason=analysis.reason or "image analysis failed",
                    direction=analysis.direction,
                    image_shape=analysis.image_shape,
                    source=source,
                )
            )
            return None

        observation = CalibrationObservation(
            robot_position=robot_position,
            image_center=np.array(
                [analysis.observation.x, analysis.observation.y],
                dtype=np.float64,
            ),
            radius=analysis.observation.radius,
            sigma=analysis.observation.sigma,
            direction=analysis.direction,
            image_shape=analysis.image_shape,
            source=source,
        )
        return self.add_observation(observation, fit=fit)

    def fit(self) -> CalibrationResult:
        """
            Fit the camera model to all currently valid observations.

            Radius outliers and calibration outliers are excluded from the resulting
            camera model, but remain stored in the session. A fit that does not
            converge, or that produces non-finite parameters, raises ``ValueError``
            and leaves the previous successful result unchanged.
        """
        try:
            if not self.can_fit:
                raise ValueError(
                    f"At least {self.min_observations} valid observations are "
                    f"required, got {self.n_observations}"
                )

            radii = np.array(
                [observation.radius for observation in self._observations],
                dtype=np.float64,
            )
            sigmas = np.array(
                [observation.sigma for observation in self._observations],
                dtype=np.float64,
            )

            fit_observation_indices = self._fit_indices(radii, sigmas)
            if len(fit_observation_indices) < self.min_observations:
                raise ValueError(
                    f"At least {self.min_observations} observations are required "
                    "after radius filtering, got "
                    f"{len(fit_observation_indices)}"
                )

            image_size_xy = self.image_size_xy
            if image_size_xy is None:
                raise ValueError("Cannot fit without an image size")

            robot_positions = np.array(
                [observation.robot_position for observation in self._observations],
                dtype=np.float64,
            )[fit_observation_indices]
            center_points = np.array(
                [observation.image_center for observation in self._observations],
                dtype=np.float64,
            )[fit_observation_indices]

            (
                pos_home,
                center_points_adjusted,
                intrinsic_matrix,
                extrinsic_matrix,
                distortion,
                optimize_result,
                rmse,
                fit_mask,
                n_distortion_coefs,
            ) = get_calibration_data(
                robot_positions,
                center_points,
                radii[fit_observation_indices],
                sigmas[fit_observation_indices],
                image_size_xy,
                self.settings,
                self.print_debug,
            )

            _validate_fit_output(
                pos_home=pos_home,
                center_points_adjusted=center_points_adjusted,
                intrinsic_matrix=intrinsic_matrix,
                extrinsic_matrix=extrinsic_matrix,
                distortion=distortion,
                optimize_result=optimize_result,
                rmse=rmse,
                n_fit_points=len(fit_observation_indices),
            )

            fit_mask = np.asarray(fit_mask, dtype=bool)
            if fit_mask.shape != fit_observation_indices.shape:
                raise ValueError(
                    "Calibration returned an outlier mask with an unexpected shape: "
                    f"{fit_mask.shape} vs {fit_observation_indices.shape}"
                )
            if not np.any(fit_mask):
                raise ValueError("Calibration rejected all observations")

            used_mask = np.zeros(self.n_observations, dtype=bool)
            used_mask[fit_observation_indices[fit_mask]] = True

            result = CalibrationResult(
                pos_home=np.asarray(pos_home),
                center_points_adjusted=np.asarray(center_points_adjusted),
                intrinsic_matrix=np.asarray(intrinsic_matrix),
                extrinsic_matrix=np.asarray(extrinsic_matrix),
                distortion=np.asarray(distortion),
                optimize_result=optimize_result,
                rmse=float(rmse),
                used_mask=used_mask,
                fit_observation_indices=fit_observation_indices,
                fit_mask=fit_mask,
                n_distortion_coefs=int(n_distortion_coefs),
                image_size_xy=image_size_xy,
                observation_count=self.n_observations,
            )
        except Exception as exc:
            self._last_fit_error = f"{type(exc).__name__}: {exc}"
            raise

        self._last_result = result
        self._fit_count += 1
        self._new_since_fit = 0
        self._last_fit_error = None
        return result

    def request_stop(self, detail: str | None = None) -> None:
        """Request an explicit stop; readiness still requires minimum observations."""
        self._explicit_stop_detail = detail or "stop requested explicitly"

    def finish_if_ready(self) -> CalibrationResult | None:
        """Return a final fit if the stop policy is ready, otherwise return None."""
        if not self.is_ready:
            return None
        return self.finish()

    def finish(self) -> CalibrationResult:
        """
            Return an up-to-date final fit, performing one if necessary.

            This method guarantees that observations added since the last successful
            fit are included before the result is returned.
        """
        if not self._observations:
            raise ValueError("No valid observations are available")
        if (
            self._last_result is not None
            and self._new_since_fit == 0
            and self._last_fit_error is None
        ):
            return self._last_result
        return self.fit()
