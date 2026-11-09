# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Saturation-based readiness policy for incremental calibration sessions."""

__all__ = [
    "DEFAULT_READINESS_CHECKPOINT_INTERVAL",
    "DEFAULT_READINESS_DISTORTION_TOLERANCE",
    "DEFAULT_READINESS_ENABLED",
    "DEFAULT_READINESS_FOCAL_RELATIVE_TOLERANCE",
    "DEFAULT_READINESS_HOME_TOLERANCE_MM",
    "DEFAULT_READINESS_MIN_INLIER_FRACTION",
    "DEFAULT_READINESS_PRINCIPAL_POINT_TOLERANCE_PX",
    "DEFAULT_READINESS_ROTATION_TOLERANCE_DEG",
    "DEFAULT_READINESS_STABLE_CHECKPOINTS",
    "DEFAULT_READINESS_TRANSLATION_TOLERANCE_MM",
    "FitSnapshot",
    "ReadinessPolicy",
    "ReadinessStatus",
    "ReadinessTolerances",
]

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import acos, ceil, degrees, isfinite

import numpy as np

from .models import CalibrationResult
from .stop import StopReason, StopStatus


DEFAULT_READINESS_ENABLED = True
DEFAULT_READINESS_CHECKPOINT_INTERVAL = 10
DEFAULT_READINESS_STABLE_CHECKPOINTS = 3
DEFAULT_READINESS_MIN_INLIER_FRACTION = 0.9
DEFAULT_READINESS_FOCAL_RELATIVE_TOLERANCE = 1e-3
DEFAULT_READINESS_PRINCIPAL_POINT_TOLERANCE_PX = 0.05
DEFAULT_READINESS_TRANSLATION_TOLERANCE_MM = 0.05
DEFAULT_READINESS_ROTATION_TOLERANCE_DEG = 0.01
DEFAULT_READINESS_HOME_TOLERANCE_MM = 0.05
DEFAULT_READINESS_DISTORTION_TOLERANCE = 1e-4


@dataclass(frozen=True)
class FitSnapshot:
    """The fitted quantities used by the saturation test.

    The nozzle position is deliberately not part of this snapshot. Readiness
    asks whether more images would change the camera calibration, not whether
    the nozzle position has a small absolute uncertainty.
    """

    n_observations: int
    n_used: int
    fx: float
    fy: float
    cx: float
    cy: float
    distortion: np.ndarray
    rotation: np.ndarray
    translation: np.ndarray
    pos_home: np.ndarray
    n_distortion_coefs: int
    rmse: float

    @classmethod
    def from_result(cls, result: CalibrationResult) -> "FitSnapshot":
        """Extract a compact snapshot from one successful calibration result."""
        intrinsic = np.asarray(result.intrinsic_matrix, dtype=np.float64)
        extrinsic = np.asarray(result.extrinsic_matrix, dtype=np.float64)
        n_distortion_coefs = int(result.n_distortion_coefs)
        return cls(
            n_observations=int(result.observation_count),
            n_used=int(result.n_used),
            fx=float(intrinsic[0, 0]),
            fy=float(intrinsic[1, 1]),
            cx=float(intrinsic[0, 2]),
            cy=float(intrinsic[1, 2]),
            distortion=np.asarray(
                result.distortion[:n_distortion_coefs],
                dtype=np.float64,
            ).copy(),
            rotation=extrinsic[:3, :3].copy(),
            translation=extrinsic[:3, 3].copy(),
            pos_home=np.asarray(result.pos_home, dtype=np.float64).copy(),
            n_distortion_coefs=n_distortion_coefs,
            rmse=float(result.rmse),
        )


@dataclass(frozen=True)
class _MeanSnapshot:
    """Window mean of the scalar and vector fit quantities."""

    fx: float
    fy: float
    cx: float
    cy: float
    distortion: np.ndarray
    rotation: np.ndarray
    translation: np.ndarray
    pos_home: np.ndarray


@dataclass(frozen=True)
class ReadinessTolerances:
    """Practical-change thresholds used by the saturation test."""

    focal_relative: float = DEFAULT_READINESS_FOCAL_RELATIVE_TOLERANCE
    principal_point_px: float = DEFAULT_READINESS_PRINCIPAL_POINT_TOLERANCE_PX
    translation_mm: float = DEFAULT_READINESS_TRANSLATION_TOLERANCE_MM
    rotation_deg: float = DEFAULT_READINESS_ROTATION_TOLERANCE_DEG
    home_mm: float = DEFAULT_READINESS_HOME_TOLERANCE_MM
    distortion: float = DEFAULT_READINESS_DISTORTION_TOLERANCE

    def __post_init__(self) -> None:
        for name in (
            "focal_relative",
            "principal_point_px",
            "translation_mm",
            "rotation_deg",
            "home_mm",
            "distortion",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"readiness tolerance {name} must be finite and positive, "
                    f"got {value}"
                )


@dataclass(frozen=True)
class ReadinessStatus:
    """Result of evaluating the saturation-based readiness policy."""

    ready: bool
    reason: StopReason
    detail: str | None = None
    saturation_ratio: float | None = None
    failed_parameter: str | None = None
    forced: bool = False


@dataclass(frozen=True)
class ReadinessPolicy:
    """Decide whether more observations are likely to change the calibration.

    The policy compares two windows of fit checkpoints. It is intentionally
    based on observed parameter stability, not on formal parameter covariance:
    covariance keeps shrinking with more data even when systematic errors have
    already placed a floor on the achievable estimate.
    """

    enabled: bool = DEFAULT_READINESS_ENABLED
    checkpoint_interval: int = DEFAULT_READINESS_CHECKPOINT_INTERVAL
    stable_checkpoints: int = DEFAULT_READINESS_STABLE_CHECKPOINTS
    min_inlier_fraction: float = DEFAULT_READINESS_MIN_INLIER_FRACTION
    tolerances: ReadinessTolerances = field(default_factory=ReadinessTolerances)

    def __post_init__(self) -> None:
        interval = int(self.checkpoint_interval)
        stable = int(self.stable_checkpoints)
        inlier_fraction = float(self.min_inlier_fraction)

        if interval < 1:
            raise ValueError(
                "readiness checkpoint_interval must be positive, "
                f"got {self.checkpoint_interval}"
            )
        if stable < 1:
            raise ValueError(
                "readiness stable_checkpoints must be positive, "
                f"got {self.stable_checkpoints}"
            )
        if not 0.0 < inlier_fraction <= 1.0:
            raise ValueError(
                "readiness min_inlier_fraction must be in (0, 1], "
                f"got {self.min_inlier_fraction}"
            )

        object.__setattr__(self, "checkpoint_interval", interval)
        object.__setattr__(self, "stable_checkpoints", stable)
        object.__setattr__(self, "min_inlier_fraction", inlier_fraction)

    def evaluate(
        self,
        stop_status: StopStatus,
        *,
        last_result: CalibrationResult | None,
        last_fit_error: str | None,
        new_since_fit: int,
        n_observations: int,
        snapshots: Sequence[FitSnapshot],
        used_directions: Sequence[int] | None = None,
    ) -> ReadinessStatus:
        """Return whether the calibration has saturated.

        The count policy remains responsible for the minimum number of
        observations and for explicit/maximum stops. This method adds the
        saturation and fit-health checks on top of it.
        """
        if not stop_status.ready:
            return ReadinessStatus(
                ready=False,
                reason=stop_status.reason,
                detail=stop_status.detail,
            )

        if not self.enabled:
            return ReadinessStatus(
                ready=True,
                reason=stop_status.reason,
                detail=stop_status.detail,
            )

        # Explicit and maximum stops are operator/safety overrides. They must
        # still be able to finalize a fit, but they are marked as forced.
        if stop_status.reason in (
            StopReason.EXPLICIT,
            StopReason.MAX_OBSERVATIONS,
        ):
            return ReadinessStatus(
                ready=True,
                reason=stop_status.reason,
                detail=(
                    f"{stop_status.detail or stop_status.reason.value}; "
                    "saturation was not evaluated"
                ),
                forced=True,
            )

        if last_fit_error is not None:
            return ReadinessStatus(
                ready=False,
                reason=StopReason.FIT_FAILED,
                detail=last_fit_error,
            )

        if last_result is None:
            return ReadinessStatus(
                ready=False,
                reason=StopReason.STALE_FIT,
                detail="no successful fit is available yet",
            )

        if (
            new_since_fit > 0
            or int(last_result.observation_count) != int(n_observations)
        ):
            return ReadinessStatus(
                ready=False,
                reason=StopReason.STALE_FIT,
                detail=(
                    f"latest fit used {last_result.observation_count} observations, "
                    f"but {n_observations} are stored"
                ),
            )

        n_used = int(last_result.n_used)
        required_inliers = ceil(self.min_inlier_fraction * n_observations)
        if n_used < required_inliers:
            return ReadinessStatus(
                ready=False,
                reason=StopReason.INSUFFICIENT_INLIERS,
                detail=(
                    f"{n_used} of {n_observations} observations survived filtering; "
                    f"at least {required_inliers} are required"
                ),
            )

        if used_directions is not None:
            directions = {int(value) for value in used_directions}
            if len(directions) > 1 or not directions.issubset({-1, 1}):
                return ReadinessStatus(
                    ready=False,
                    reason=StopReason.MIXED_DIRECTIONS,
                    detail=(
                        "the observations used by the fit contain mixed or "
                        f"invalid nozzle directions: {sorted(directions)}"
                    ),
                )

        if not snapshots:
            return ReadinessStatus(
                ready=False,
                reason=StopReason.WAITING_FOR_CHECKPOINTS,
                detail=(
                    "no fit checkpoints are available; "
                    f"{2 * self.stable_checkpoints} are required"
                ),
            )

        latest_distortion_coefs = snapshots[-1].n_distortion_coefs
        compatible: list[FitSnapshot] = []
        for snapshot in reversed(snapshots):
            if snapshot.n_distortion_coefs != latest_distortion_coefs:
                break
            compatible.append(snapshot)
        compatible.reverse()
        required_checkpoints = 2 * self.stable_checkpoints
        if len(compatible) < required_checkpoints:
            return ReadinessStatus(
                ready=False,
                reason=StopReason.WAITING_FOR_CHECKPOINTS,
                detail=(
                    f"{len(compatible)} of {required_checkpoints} compatible "
                    "fit checkpoints are available"
                ),
            )

        previous = compatible[-required_checkpoints:-self.stable_checkpoints]
        recent = compatible[-self.stable_checkpoints:]
        checks = self._parameter_checks(previous, recent)
        failed = max(checks, key=lambda check: check[1])
        if failed[1] <= 1.0:
            return ReadinessStatus(
                ready=True,
                reason=StopReason.SATURATED,
                detail=(
                    f"saturated over {required_checkpoints} checkpoints "
                    f"(max change ratio {failed[1]:.2f})"
                ),
                saturation_ratio=failed[1],
            )

        return ReadinessStatus(
            ready=False,
            reason=StopReason.NOT_SATURATED,
            detail=(
                f"not saturated: {failed[0]} {failed[2]} "
                f"(ratio {failed[1]:.2f})"
            ),
            saturation_ratio=failed[1],
            failed_parameter=failed[0],
        )

    def _parameter_checks(
        self,
        previous: Sequence[FitSnapshot],
        recent: Sequence[FitSnapshot],
    ) -> list[tuple[str, float, str]]:
        """Return (parameter, normalized change, display detail) tuples."""
        old = self._mean_snapshot(previous)
        new = self._mean_snapshot(recent)
        tolerances = self.tolerances
        checks: list[tuple[str, float, str]] = []

        def add(
            name: str,
            change: float,
            tolerance: float,
            unit: str,
        ) -> None:
            ratio = float(change) / float(tolerance)
            checks.append(
                (
                    name,
                    ratio,
                    f"change {change:.4g} {unit} (limit {tolerance:.4g} {unit})",
                )
            )

        for name in ("fx", "fy"):
            old_value = float(getattr(old, name))
            new_value = float(getattr(new, name))
            scale = max(abs(old_value), abs(new_value), 1.0)
            relative_change = abs(new_value - old_value) / scale
            add(
                name,
                relative_change,
                tolerances.focal_relative,
                "relative",
            )

        for name in ("cx", "cy"):
            add(
                name,
                abs(float(getattr(new, name)) - float(getattr(old, name))),
                tolerances.principal_point_px,
                "px",
            )

        translation_change = float(
            np.linalg.norm(new.translation - old.translation)
        )
        add(
            "translation",
            translation_change,
            tolerances.translation_mm,
            "mm",
        )

        rotation_change = _rotation_angle_deg(
            old.rotation,
            new.rotation,
        )
        add(
            "rotation",
            rotation_change,
            tolerances.rotation_deg,
            "deg",
        )

        home_change = float(np.linalg.norm(new.pos_home - old.pos_home))
        add("pos_home", home_change, tolerances.home_mm, "mm")

        if new.distortion.size:
            distortion_change = float(
                np.max(np.abs(new.distortion - old.distortion))
            )
            add(
                "distortion",
                distortion_change,
                tolerances.distortion,
                "absolute",
            )

        return checks

    @staticmethod
    def _mean_snapshot(snapshots: Sequence[FitSnapshot]) -> _MeanSnapshot:
        """Average scalar and array fields over one checkpoint window."""
        count = len(snapshots)
        return _MeanSnapshot(
            fx=sum(snapshot.fx for snapshot in snapshots) / count,
            fy=sum(snapshot.fy for snapshot in snapshots) / count,
            cx=sum(snapshot.cx for snapshot in snapshots) / count,
            cy=sum(snapshot.cy for snapshot in snapshots) / count,
            distortion=np.mean(
                np.stack([snapshot.distortion for snapshot in snapshots]),
                axis=0,
            ),
            rotation=np.mean(
                np.stack([snapshot.rotation for snapshot in snapshots]),
                axis=0,
            ),
            translation=np.mean(
                np.stack([snapshot.translation for snapshot in snapshots]),
                axis=0,
            ),
            pos_home=np.mean(
                np.stack([snapshot.pos_home for snapshot in snapshots]),
                axis=0,
            ),
        )


def _rotation_angle_deg(first: np.ndarray, second: np.ndarray) -> float:
    """Return the geodesic angle between two rotation matrices in degrees."""
    relative = np.asarray(first, dtype=np.float64).T @ np.asarray(
        second,
        dtype=np.float64,
    )
    cosine = (float(np.trace(relative)) - 1.0) / 2.0
    return degrees(acos(float(np.clip(cosine, -1.0, 1.0))))
