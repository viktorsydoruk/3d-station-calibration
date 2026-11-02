# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass
class plantQuantities:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::plantQuantities``.
    """
    plantID: int = 0
    timeNbr: int = 0
    germinationDate: int = 0
    nbrOfLeaves: float = 0.0
    nbrOfGreenLeaves: float = 0.0
    nbrOfYellowLeaves: float = 0.0
    meanLeafSize: float = 0.0
    smallestLeafSize: float = 0.0
    largestLeafSize: float = 0.0
    plantTallness: float = 0.0
    meanGrowthRate: float = 0.0
    largestLeafGrowthRate: float = 0.0
    airTemperature: float = 0.0
    airHumidity: float = 0.0
    lightIntensity: float = 0.0
    percentageOfLight: float = 0.0

_Phyto_Common_plantQuantities_t = IcePy.defineStruct(
    "::Phyto::Common::plantQuantities",
    plantQuantities,
    (),
    (
        ("plantID", (), IcePy._t_long),
        ("timeNbr", (), IcePy._t_long),
        ("germinationDate", (), IcePy._t_long),
        ("nbrOfLeaves", (), IcePy._t_double),
        ("nbrOfGreenLeaves", (), IcePy._t_double),
        ("nbrOfYellowLeaves", (), IcePy._t_double),
        ("meanLeafSize", (), IcePy._t_double),
        ("smallestLeafSize", (), IcePy._t_double),
        ("largestLeafSize", (), IcePy._t_double),
        ("plantTallness", (), IcePy._t_double),
        ("meanGrowthRate", (), IcePy._t_double),
        ("largestLeafGrowthRate", (), IcePy._t_double),
        ("airTemperature", (), IcePy._t_double),
        ("airHumidity", (), IcePy._t_double),
        ("lightIntensity", (), IcePy._t_double),
        ("percentageOfLight", (), IcePy._t_double)
    ))

__all__ = ["plantQuantities", "_Phyto_Common_plantQuantities_t"]
