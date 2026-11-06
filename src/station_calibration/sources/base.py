# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Protocols shared by calibration observation sources."""

__all__ = [
    "ObservationDataset",
    "ObservationSource",
]

from typing import Protocol

from ..models import CalibrationObservation, ObservationRejection


class ObservationDataset(Protocol):
    """Data produced by a source before it is fed into a calibration session."""

    observations: tuple[CalibrationObservation, ...]
    rejections: tuple[ObservationRejection, ...]
    image_size_xy: tuple[int, int]

    @property
    def apply_radius_filter(self) -> bool:
        """Whether the session should apply radius filtering to these observations."""


class ObservationSource(Protocol):
    """A source that can load one dataset of observations and rejections."""

    def load(self) -> ObservationDataset:
        """Load observations and rejections from the source."""
