# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass(order=True, unsafe_hash=True)
class segmentationParams:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::segmentationParams``.
    """
    Hmin: int = 0
    Hmax: int = 0
    Smin: int = 0
    Smax: int = 0
    Vmin: int = 0
    Vmax: int = 0
    minSizeObj: int = 0
    maxSizeObj: int = 0
    minSizeHoles: int = 0
    structureElement: int = 0

_CommonPhenoseeder_segmentationParams_t = IcePy.defineStruct(
    "::CommonPhenoseeder::segmentationParams",
    segmentationParams,
    (),
    (
        ("Hmin", (), IcePy._t_int),
        ("Hmax", (), IcePy._t_int),
        ("Smin", (), IcePy._t_int),
        ("Smax", (), IcePy._t_int),
        ("Vmin", (), IcePy._t_int),
        ("Vmax", (), IcePy._t_int),
        ("minSizeObj", (), IcePy._t_int),
        ("maxSizeObj", (), IcePy._t_int),
        ("minSizeHoles", (), IcePy._t_int),
        ("structureElement", (), IcePy._t_int)
    ))

__all__ = ["segmentationParams", "_CommonPhenoseeder_segmentationParams_t"]
