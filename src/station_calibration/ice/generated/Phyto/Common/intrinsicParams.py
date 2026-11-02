# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.INTRINSICMODEL import INTRINSICMODEL
from Phyto.Common.INTRINSICMODEL import _Phyto_Common_INTRINSICMODEL_t

from Phyto.Common.doubleVec import _Phyto_Common_doubleVec_t

from dataclasses import dataclass
from dataclasses import field


@dataclass
class intrinsicParams:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::intrinsicParams``.
    """
    modelId: INTRINSICMODEL = INTRINSICMODEL.INTRINSICUNKNOWN
    modelParams: list[float] = field(default_factory=list)

_Phyto_Common_intrinsicParams_t = IcePy.defineStruct(
    "::Phyto::Common::intrinsicParams",
    intrinsicParams,
    (),
    (
        ("modelId", (), _Phyto_Common_INTRINSICMODEL_t),
        ("modelParams", (), _Phyto_Common_doubleVec_t)
    ))

__all__ = ["intrinsicParams", "_Phyto_Common_intrinsicParams_t"]
