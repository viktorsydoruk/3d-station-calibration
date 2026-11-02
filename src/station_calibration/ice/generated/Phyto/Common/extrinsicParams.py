# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.BOOLFLAG import BOOLFLAG
from Phyto.Common.BOOLFLAG import _Phyto_Common_BOOLFLAG_t

from Phyto.Common.COORDINATESYSTEM import COORDINATESYSTEM
from Phyto.Common.COORDINATESYSTEM import _Phyto_Common_COORDINATESYSTEM_t

from Phyto.Common.EXTRINSICMODEL import EXTRINSICMODEL
from Phyto.Common.EXTRINSICMODEL import _Phyto_Common_EXTRINSICMODEL_t

from Phyto.Common.doubleVec import _Phyto_Common_doubleVec_t

from dataclasses import dataclass
from dataclasses import field


@dataclass
class extrinsicParams:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::extrinsicParams``.
    """
    modelId: EXTRINSICMODEL = EXTRINSICMODEL.EXTRINSICUNKNOWN
    isAbsolute: BOOLFLAG = BOOLFLAG.BFUNHANDLED
    coordsys: COORDINATESYSTEM = COORDINATESYSTEM.CAM
    coordSysIndex: int = 0
    modelParams: list[float] = field(default_factory=list)

_Phyto_Common_extrinsicParams_t = IcePy.defineStruct(
    "::Phyto::Common::extrinsicParams",
    extrinsicParams,
    (),
    (
        ("modelId", (), _Phyto_Common_EXTRINSICMODEL_t),
        ("isAbsolute", (), _Phyto_Common_BOOLFLAG_t),
        ("coordsys", (), _Phyto_Common_COORDINATESYSTEM_t),
        ("coordSysIndex", (), IcePy._t_int),
        ("modelParams", (), _Phyto_Common_doubleVec_t)
    ))

__all__ = ["extrinsicParams", "_Phyto_Common_extrinsicParams_t"]
