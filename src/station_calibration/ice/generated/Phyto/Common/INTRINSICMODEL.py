# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class INTRINSICMODEL(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::INTRINSICMODEL``.
    """

    INTRINSICUNKNOWN = 0

    INTRINSICFFSPP = 1

    INTRINSICMATRIX = 2

_Phyto_Common_INTRINSICMODEL_t = IcePy.defineEnum(
    "::Phyto::Common::INTRINSICMODEL",
    INTRINSICMODEL,
    (),
    {
        0: INTRINSICMODEL.INTRINSICUNKNOWN,
        1: INTRINSICMODEL.INTRINSICFFSPP,
        2: INTRINSICMODEL.INTRINSICMATRIX,
    }
)

__all__ = ["INTRINSICMODEL", "_Phyto_Common_INTRINSICMODEL_t"]
