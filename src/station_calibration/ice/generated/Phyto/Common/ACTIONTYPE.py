# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class ACTIONTYPE(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::ACTIONTYPE``.
    """

    WATERING = 0

    NURTURE = 1

    LIGHT = 2

_Phyto_Common_ACTIONTYPE_t = IcePy.defineEnum(
    "::Phyto::Common::ACTIONTYPE",
    ACTIONTYPE,
    (),
    {
        0: ACTIONTYPE.WATERING,
        1: ACTIONTYPE.NURTURE,
        2: ACTIONTYPE.LIGHT,
    }
)

__all__ = ["ACTIONTYPE", "_Phyto_Common_ACTIONTYPE_t"]
