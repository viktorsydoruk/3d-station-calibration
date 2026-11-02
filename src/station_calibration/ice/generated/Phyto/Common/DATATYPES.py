# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class DATATYPES(Enum):
    """
    ////////////////////////////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////////////////////////////
    
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::DATATYPES``.
    """

    DTUNSPECIFIED = 0

    DTICELONG = 1

    DTIMAGEDATA = 2

    DTACQDATA = 3

    DTICEDOUBLE = 4

_Phyto_Common_DATATYPES_t = IcePy.defineEnum(
    "::Phyto::Common::DATATYPES",
    DATATYPES,
    (),
    {
        0: DATATYPES.DTUNSPECIFIED,
        1: DATATYPES.DTICELONG,
        2: DATATYPES.DTIMAGEDATA,
        3: DATATYPES.DTACQDATA,
        4: DATATYPES.DTICEDOUBLE,
    }
)

__all__ = ["DATATYPES", "_Phyto_Common_DATATYPES_t"]
