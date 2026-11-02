# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass
class Point:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phenoseeder::Point``.
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

_Phenoseeder_Point_t = IcePy.defineStruct(
    "::Phenoseeder::Point",
    Point,
    (),
    (
        ("x", (), IcePy._t_double),
        ("y", (), IcePy._t_double),
        ("z", (), IcePy._t_double)
    ))

__all__ = ["Point", "_Phenoseeder_Point_t"]
