# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass
class Measurement:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::Measurement``.
    """
    comment: str = ""
    value: float = 0.0
    unitId: int = 0
    traitId: int = 0

_CommonPhenoseeder_Measurement_t = IcePy.defineStruct(
    "::CommonPhenoseeder::Measurement",
    Measurement,
    (),
    (
        ("comment", (), IcePy._t_string),
        ("value", (), IcePy._t_double),
        ("unitId", (), IcePy._t_int),
        ("traitId", (), IcePy._t_int)
    ))

__all__ = ["Measurement", "_CommonPhenoseeder_Measurement_t"]
