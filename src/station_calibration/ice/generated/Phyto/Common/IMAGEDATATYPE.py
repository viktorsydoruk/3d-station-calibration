# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class IMAGEDATATYPE(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::IMAGEDATATYPE``.
    """

    IDTUNKNOWN = 0

    IDTBOOL = 1

    IDTBYTE = 2

    IDTSHORT = 3

    IDTFLOAT = 4

    IDTDOUBLE = 5

_Phyto_Common_IMAGEDATATYPE_t = IcePy.defineEnum(
    "::Phyto::Common::IMAGEDATATYPE",
    IMAGEDATATYPE,
    (),
    {
        0: IMAGEDATATYPE.IDTUNKNOWN,
        1: IMAGEDATATYPE.IDTBOOL,
        2: IMAGEDATATYPE.IDTBYTE,
        3: IMAGEDATATYPE.IDTSHORT,
        4: IMAGEDATATYPE.IDTFLOAT,
        5: IMAGEDATATYPE.IDTDOUBLE,
    }
)

__all__ = ["IMAGEDATATYPE", "_Phyto_Common_IMAGEDATATYPE_t"]
