# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.vecOfDoubles import _CommonPhenoseeder_vecOfDoubles_t

from dataclasses import dataclass
from dataclasses import field


@dataclass
class extrinsicParams:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::extrinsicParams``.
    """
    rotation: list[float] = field(default_factory=list)
    translation: list[float] = field(default_factory=list)

_Phyto_Common_extrinsicParams_t = IcePy.defineStruct(
    "::Phyto::Common::extrinsicParams",
    extrinsicParams,
    (),
    (
        ("rotation", (), _CommonPhenoseeder_vecOfDoubles_t),
        ("translation", (), _CommonPhenoseeder_vecOfDoubles_t)
    ))

__all__ = ["extrinsicParams", "_Phyto_Common_extrinsicParams_t"]
