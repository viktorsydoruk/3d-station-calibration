# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.Point import Point
from CommonPhenoseeder.Point import _CommonPhenoseeder_Point_t

from dataclasses import dataclass
from dataclasses import field


@dataclass(order=True, unsafe_hash=True)
class PotAllocation:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::PotAllocation``.
    """
    seedId: int = 0
    position: Point = field(default_factory=Point)

_CommonPhenoseeder_PotAllocation_t = IcePy.defineStruct(
    "::CommonPhenoseeder::PotAllocation",
    PotAllocation,
    (),
    (
        ("seedId", (), IcePy._t_long),
        ("position", (), _CommonPhenoseeder_Point_t)
    ))

__all__ = ["PotAllocation", "_CommonPhenoseeder_PotAllocation_t"]
