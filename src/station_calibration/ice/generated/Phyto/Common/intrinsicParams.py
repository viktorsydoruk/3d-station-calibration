# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.vecOfDoubles import _CommonPhenoseeder_vecOfDoubles_t

from dataclasses import dataclass
from dataclasses import field


@dataclass
class intrinsicParams:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::intrinsicParams``.
    """
    matrix: list[float] = field(default_factory=list)

_Phyto_Common_intrinsicParams_t = IcePy.defineStruct(
    "::Phyto::Common::intrinsicParams",
    intrinsicParams,
    (),
    (("matrix", (), _CommonPhenoseeder_vecOfDoubles_t),))

__all__ = ["intrinsicParams", "_Phyto_Common_intrinsicParams_t"]
