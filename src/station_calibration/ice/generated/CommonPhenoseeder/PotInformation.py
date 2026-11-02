# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass
class PotInformation:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::PotInformation``.
    """
    potWidth: float = 0.0
    potHeight: float = 0.0
    potDepth: float = 0.0

_CommonPhenoseeder_PotInformation_t = IcePy.defineStruct(
    "::CommonPhenoseeder::PotInformation",
    PotInformation,
    (),
    (
        ("potWidth", (), IcePy._t_double),
        ("potHeight", (), IcePy._t_double),
        ("potDepth", (), IcePy._t_double)
    ))

__all__ = ["PotInformation", "_CommonPhenoseeder_PotInformation_t"]
