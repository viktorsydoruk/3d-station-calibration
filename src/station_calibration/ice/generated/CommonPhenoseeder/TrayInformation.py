# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass
class TrayInformation:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::TrayInformation``.
    """
    intermediateAreaX: float = 0.0
    intermediateAreaY: float = 0.0
    numberOfPotsX: int = 0
    numberOfPotsY: int = 0
    offsetSeedingHeight: float = 0.0
    offsetToBaseX: float = 0.0
    offsetToBaseY: float = 0.0
    offsetToBaseZ: float = 0.0

_CommonPhenoseeder_TrayInformation_t = IcePy.defineStruct(
    "::CommonPhenoseeder::TrayInformation",
    TrayInformation,
    (),
    (
        ("intermediateAreaX", (), IcePy._t_double),
        ("intermediateAreaY", (), IcePy._t_double),
        ("numberOfPotsX", (), IcePy._t_int),
        ("numberOfPotsY", (), IcePy._t_int),
        ("offsetSeedingHeight", (), IcePy._t_double),
        ("offsetToBaseX", (), IcePy._t_double),
        ("offsetToBaseY", (), IcePy._t_double),
        ("offsetToBaseZ", (), IcePy._t_double)
    ))

__all__ = ["TrayInformation", "_CommonPhenoseeder_TrayInformation_t"]
