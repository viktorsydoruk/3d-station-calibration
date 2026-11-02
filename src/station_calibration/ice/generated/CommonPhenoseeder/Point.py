# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass(order=True, unsafe_hash=True)
class Point:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::Point``.
    """
    x: int = 0
    y: int = 0

_CommonPhenoseeder_Point_t = IcePy.defineStruct(
    "::CommonPhenoseeder::Point",
    Point,
    (),
    (
        ("x", (), IcePy._t_int),
        ("y", (), IcePy._t_int)
    ))

__all__ = ["Point", "_CommonPhenoseeder_Point_t"]
