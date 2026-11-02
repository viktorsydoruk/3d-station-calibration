# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class EXTRINSICMODEL(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::EXTRINSICMODEL``.
    """

    EXTRINSICUNKNOWN = 0

    EXTRINSICEULER = 1

    EXTRINSICRODRIGUES = 2

    EXTRINSICROTMATRIX = 3

_Phyto_Common_EXTRINSICMODEL_t = IcePy.defineEnum(
    "::Phyto::Common::EXTRINSICMODEL",
    EXTRINSICMODEL,
    (),
    {
        0: EXTRINSICMODEL.EXTRINSICUNKNOWN,
        1: EXTRINSICMODEL.EXTRINSICEULER,
        2: EXTRINSICMODEL.EXTRINSICRODRIGUES,
        3: EXTRINSICMODEL.EXTRINSICROTMATRIX,
    }
)

__all__ = ["EXTRINSICMODEL", "_Phyto_Common_EXTRINSICMODEL_t"]
