# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Stop/readiness policy for incremental calibration sessions."""

__all__ = [
    "DEFAULT_TARGET_OBSERVATIONS",
    "StopReason",
    "StopPolicy",
    "StopStatus",
]

from dataclasses import dataclass
from enum import StrEnum


DEFAULT_TARGET_OBSERVATIONS = 100


class StopReason(StrEnum):
    """Why an incremental calibration session is or is not ready."""

    NOT_READY = "not_ready"
    TARGET_OBSERVATIONS = "target_observations"
    MAX_OBSERVATIONS = "max_observations"
    EXPLICIT = "explicit"
    SATURATED = "saturated"
    NOT_SATURATED = "not_saturated"
    FIT_FAILED = "fit_failed"
    STALE_FIT = "stale_fit"
    INSUFFICIENT_INLIERS = "insufficient_inliers"
    MIXED_DIRECTIONS = "mixed_directions"
    WAITING_FOR_CHECKPOINTS = "waiting_for_checkpoints"


@dataclass(frozen=True)
class StopStatus:
    """Result of evaluating a :class:`StopPolicy` against a session state."""

    ready: bool
    reason: StopReason
    detail: str | None = None


@dataclass(frozen=True)
class StopPolicy:
    """
        Readiness rule for a calibration session.

        ``target_observations`` is the normal readiness target. ``max_observations``
        is an optional earlier readiness threshold. Set either field to ``None`` to
        disable it. An explicit stop request is handled by the session and takes
        precedence over both counters. Readiness is advisory: the session keeps
        accepting observations until the caller calls ``finish()`` or aborts.
    """

    target_observations: int | None = DEFAULT_TARGET_OBSERVATIONS
    max_observations: int | None = None

    def __post_init__(self) -> None:
        if self.target_observations is not None:
            target = int(self.target_observations)
            if target < 1:
                raise ValueError(
                    "target_observations must be positive or None, "
                    f"got {self.target_observations}"
                )
            object.__setattr__(self, "target_observations", target)

        if self.max_observations is not None:
            maximum = int(self.max_observations)
            if maximum < 1:
                raise ValueError(
                    "max_observations must be positive or None, "
                    f"got {self.max_observations}"
                )
            object.__setattr__(self, "max_observations", maximum)

    def evaluate(self,
                 n_observations: int,
                 min_observations: int,
                 *,
                 explicit_detail: str | None = None) -> StopStatus:
        """
            Evaluate the policy.

        :param n_observations: number of currently valid observations
        :param min_observations: minimum needed before a fit is possible
        :param explicit_detail: non-None when a caller explicitly requested stop
        :return: readiness state and the reason for it
        """
        n_observations = int(n_observations)
        min_observations = int(min_observations)

        if n_observations < min_observations:
            detail = None
            if explicit_detail is not None:
                detail = (
                    f"{explicit_detail} (minimum of {min_observations} valid "
                    "observations not reached)"
                )
            return StopStatus(False, StopReason.NOT_READY, detail)

        if explicit_detail is not None:
            return StopStatus(True, StopReason.EXPLICIT, explicit_detail)

        if (
            self.target_observations is not None
            and n_observations >= self.target_observations
        ):
            return StopStatus(
                True,
                StopReason.TARGET_OBSERVATIONS,
                f"reached target of {self.target_observations} valid observations",
            )

        if (
            self.max_observations is not None
            and n_observations >= self.max_observations
        ):
            return StopStatus(
                True,
                StopReason.MAX_OBSERVATIONS,
                f"reached maximum of {self.max_observations} valid observations",
            )

        return StopStatus(False, StopReason.NOT_READY)
