# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass
class intrinsicParams:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::intrinsicParams``.
    """
    fx: float = 0.0
    fy: float = 0.0
    cx: float = 0.0
    cy: float = 0.0

_Phyto_Common_intrinsicParams_t = IcePy.defineStruct(
    "::Phyto::Common::intrinsicParams",
    intrinsicParams,
    (),
    (
        ("fx", (), IcePy._t_double),
        ("fy", (), IcePy._t_double),
        ("cx", (), IcePy._t_double),
        ("cy", (), IcePy._t_double)
    ))

__all__ = ["intrinsicParams", "_Phyto_Common_intrinsicParams_t"]
