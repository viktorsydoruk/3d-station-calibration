# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class ExperimentStatus(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::CommonPhenoseeder::ExperimentStatus``.
    """

    CREATED = 0

    RUNNING = 1

    FINISHED = 2

    UNKNOWN = 3

_CommonPhenoseeder_ExperimentStatus_t = IcePy.defineEnum(
    "::CommonPhenoseeder::ExperimentStatus",
    ExperimentStatus,
    (),
    {
        0: ExperimentStatus.CREATED,
        1: ExperimentStatus.RUNNING,
        2: ExperimentStatus.FINISHED,
        3: ExperimentStatus.UNKNOWN,
    }
)

__all__ = ["ExperimentStatus", "_CommonPhenoseeder_ExperimentStatus_t"]
