# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.vecOfPoints import _CommonPhenoseeder_vecOfPoints_t

from dataclasses import dataclass
from dataclasses import field

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from CommonPhenoseeder.Point import Point


@dataclass
class orderedMap:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::orderedMap``.
    """
    first: int = 0
    second: list[Point] = field(default_factory=list)

_CommonPhenoseeder_orderedMap_t = IcePy.defineStruct(
    "::CommonPhenoseeder::orderedMap",
    orderedMap,
    (),
    (
        ("first", (), IcePy._t_int),
        ("second", (), _CommonPhenoseeder_vecOfPoints_t)
    ))

__all__ = ["orderedMap", "_CommonPhenoseeder_orderedMap_t"]
