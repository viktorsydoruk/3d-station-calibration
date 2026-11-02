# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.ACTIONTYPE import ACTIONTYPE
from Phyto.Common.ACTIONTYPE import _Phyto_Common_ACTIONTYPE_t

from dataclasses import dataclass


@dataclass
class numericAction:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::numericAction``.
    """
    type: ACTIONTYPE = ACTIONTYPE.WATERING
    executionTime: int = -1
    value: float = 0.0

_Phyto_Common_numericAction_t = IcePy.defineStruct(
    "::Phyto::Common::numericAction",
    numericAction,
    (),
    (
        ("type", (), _Phyto_Common_ACTIONTYPE_t),
        ("executionTime", (), IcePy._t_long),
        ("value", (), IcePy._t_float)
    ))

__all__ = ["numericAction", "_Phyto_Common_numericAction_t"]
