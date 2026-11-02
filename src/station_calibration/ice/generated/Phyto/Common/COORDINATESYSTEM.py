# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class COORDINATESYSTEM(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::COORDINATESYSTEM``.
    """

    WORLD = 0

    TOOL = 1

    BASE = 2

    CAM = 3

_Phyto_Common_COORDINATESYSTEM_t = IcePy.defineEnum(
    "::Phyto::Common::COORDINATESYSTEM",
    COORDINATESYSTEM,
    (),
    {
        0: COORDINATESYSTEM.WORLD,
        1: COORDINATESYSTEM.TOOL,
        2: COORDINATESYSTEM.BASE,
        3: COORDINATESYSTEM.CAM,
    }
)

__all__ = ["COORDINATESYSTEM", "_Phyto_Common_COORDINATESYSTEM_t"]
