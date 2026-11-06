# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Domain models shared by calibration sources, sessions, and interfaces."""

__all__ = [
    "CalibrationObservation",
    "ObservationRejection",
    "CalibrationResult",
    "SIGMA_OFFSET",
]

from dataclasses import dataclass

import numpy as np
from scipy.optimize import OptimizeResult


# Blur sigmas are used as weights and as a radius-bias correction.  A small
# constant offset keeps zero sigmas usable and reflects the sub-pixel uncertainty
# that is not captured by the edge-profile fit.
SIGMA_OFFSET = 0.5


@dataclass(frozen=True)
class CalibrationObservation:
    """
        One valid sphere observation together with the matching robot position.

        ``image_shape`` follows :class:`ImageAnalysisResult` and is (height, width).
    """

    robot_position: np.ndarray
    image_center: np.ndarray
    radius: float
    sigma: float
    direction: int
    image_shape: tuple[int, int]
    source: str | None = None

    def __post_init__(self) -> None:
        robot_position = np.array(self.robot_position, dtype=np.float64, copy=True)
        if robot_position.shape != (3,):
            raise ValueError(
                f"robot_position must have shape (3,), got {robot_position.shape}"
            )

        image_center = np.array(self.image_center, dtype=np.float64, copy=True)
        if image_center.shape != (2,):
            raise ValueError(
                f"image_center must have shape (2,), got {image_center.shape}"
            )

        radius = float(self.radius)
        sigma = float(self.sigma)
        direction = int(self.direction)
        image_shape = tuple(int(value) for value in self.image_shape)

        if not np.all(np.isfinite(robot_position)):
            raise ValueError("robot_position must contain only finite values")
        if not np.all(np.isfinite(image_center)):
            raise ValueError("image_center must contain only finite values")
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError(f"radius must be a positive finite value, got {radius}")
        if not np.isfinite(sigma) or sigma < 0:
            raise ValueError(f"sigma must be a non-negative finite value, got {sigma}")
        if self.direction not in (-1, 1):
            raise ValueError(f"direction must be -1 or 1, got {self.direction}")
        if len(image_shape) != 2 or any(value <= 0 for value in image_shape):
            raise ValueError(
                f"image_shape must contain two positive values, got {image_shape}"
            )

        object.__setattr__(self, "robot_position", robot_position)
        object.__setattr__(self, "image_center", image_center)
        object.__setattr__(self, "radius", radius)
        object.__setattr__(self, "sigma", sigma)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "image_shape", image_shape)


@dataclass(frozen=True)
class ObservationRejection:
    """An image that could not produce a usable observation."""

    reason: str
    direction: int = 0
    image_shape: tuple[int, int] | None = None
    source: str | None = None


@dataclass(frozen=True)
class CalibrationResult:
    """
        Result of one camera fit.

        ``center_points_adjusted`` contains one entry per observation passed to the
        fit (after radius filtering), in ``fit_observation_indices`` order.
        ``fit_mask`` marks which of those observations survived the calibration
        outlier detection. ``used_mask`` is the same selection expressed over all
        observations currently held by the session.
    """

    pos_home: np.ndarray
    center_points_adjusted: np.ndarray
    intrinsic_matrix: np.ndarray
    extrinsic_matrix: np.ndarray
    distortion: np.ndarray
    optimize_result: OptimizeResult
    rmse: float
    used_mask: np.ndarray
    fit_observation_indices: np.ndarray
    fit_mask: np.ndarray
    n_distortion_coefs: int
    image_size_xy: tuple[int, int]
    observation_count: int

    @property
    def n_used(self) -> int:
        """Number of observations used by the fit after all filtering."""
        return int(np.count_nonzero(self.used_mask))
