# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.extrinsicParams import _Phyto_Common_extrinsicParams_t
from Phyto.Common.extrinsicParams import extrinsicParams

from Phyto.Common.intrinsicParams import _Phyto_Common_intrinsicParams_t
from Phyto.Common.intrinsicParams import intrinsicParams

from dataclasses import dataclass
from dataclasses import field


@dataclass
class cameraParams:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::cameraParams``.
    """
    intrinsicCameraParams: intrinsicParams = field(default_factory=intrinsicParams)
    extrinsicCameraParams: extrinsicParams = field(default_factory=extrinsicParams)

_Phyto_Common_cameraParams_t = IcePy.defineStruct(
    "::Phyto::Common::cameraParams",
    cameraParams,
    (),
    (
        ("intrinsicCameraParams", (), _Phyto_Common_intrinsicParams_t),
        ("extrinsicCameraParams", (), _Phyto_Common_extrinsicParams_t)
    ))

__all__ = ["cameraParams", "_Phyto_Common_cameraParams_t"]
