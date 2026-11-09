# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Value objects produced by single-image analysis."""

__all__ = [
    "SphereObservation",
    "ImageAnalysisResult",
]

from dataclasses import dataclass

import numpy as np

from ..models import validate_center_covariance


@dataclass(frozen=True)
class SphereObservation:
    """Sphere parameters extracted from one image."""
    x: float
    y: float
    radius: float
    sigma: float
    center_covariance: np.ndarray | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "center_covariance",
            validate_center_covariance(self.center_covariance),
        )


@dataclass(frozen=True)
class ImageAnalysisResult:
    """Result of analyzing one image, including a reason when nothing was found."""
    observation: SphereObservation | None
    direction: int
    image_shape: tuple[int, int]
    reason: str | None = None
