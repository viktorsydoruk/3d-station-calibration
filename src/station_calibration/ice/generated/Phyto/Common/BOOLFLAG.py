# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class BOOLFLAG(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::BOOLFLAG``.
    """

    BFUNHANDLED = 0

    BFUNKNOWN = 1

    BFTRUE = 2

    BFFALSE = 3

_Phyto_Common_BOOLFLAG_t = IcePy.defineEnum(
    "::Phyto::Common::BOOLFLAG",
    BOOLFLAG,
    (),
    {
        0: BOOLFLAG.BFUNHANDLED,
        1: BOOLFLAG.BFUNKNOWN,
        2: BOOLFLAG.BFTRUE,
        3: BOOLFLAG.BFFALSE,
    }
)

__all__ = ["BOOLFLAG", "_Phyto_Common_BOOLFLAG_t"]
