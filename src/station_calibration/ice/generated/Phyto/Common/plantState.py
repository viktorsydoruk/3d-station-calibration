# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass(order=True, unsafe_hash=True)
class plantState:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::plantState``.
    """
    plantID: int = 0
    timeNbr: int = 0
    mappingID: int = 0
    nbrOfLeaves: int = 0
    nbrOfGreenLeaves: int = 0
    nbrOfYellowLeaves: int = 0
    meanLeafSize: int = 0
    smallestLeafSize: int = 0
    largestLeafSize: int = 0
    plantTallness: int = 0
    meanGrowthRate: int = 0
    largestLeafGrowthRate: int = 0
    airHumidity: int = 0
    airTemperature: int = 0
    lightIntensity: int = 0

_Phyto_Common_plantState_t = IcePy.defineStruct(
    "::Phyto::Common::plantState",
    plantState,
    (),
    (
        ("plantID", (), IcePy._t_long),
        ("timeNbr", (), IcePy._t_long),
        ("mappingID", (), IcePy._t_long),
        ("nbrOfLeaves", (), IcePy._t_int),
        ("nbrOfGreenLeaves", (), IcePy._t_int),
        ("nbrOfYellowLeaves", (), IcePy._t_int),
        ("meanLeafSize", (), IcePy._t_int),
        ("smallestLeafSize", (), IcePy._t_int),
        ("largestLeafSize", (), IcePy._t_int),
        ("plantTallness", (), IcePy._t_int),
        ("meanGrowthRate", (), IcePy._t_int),
        ("largestLeafGrowthRate", (), IcePy._t_int),
        ("airHumidity", (), IcePy._t_int),
        ("airTemperature", (), IcePy._t_int),
        ("lightIntensity", (), IcePy._t_int)
    ))

__all__ = ["plantState", "_Phyto_Common_plantState_t"]
