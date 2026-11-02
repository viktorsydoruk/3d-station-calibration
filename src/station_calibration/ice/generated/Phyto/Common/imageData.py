# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.IMAGEDATATYPE import IMAGEDATATYPE
from Phyto.Common.IMAGEDATATYPE import _Phyto_Common_IMAGEDATATYPE_t

from Phyto.Common.IMAGEFORMAT import IMAGEFORMAT
from Phyto.Common.IMAGEFORMAT import _Phyto_Common_IMAGEFORMAT_t

from Phyto.Common.boolVec import _Phyto_Common_boolVec_t

from Phyto.Common.byteVec import _Phyto_Common_byteVec_t

from Phyto.Common.cameraParams import _Phyto_Common_cameraParams_t
from Phyto.Common.cameraParams import cameraParams

from Phyto.Common.floatVec import _Phyto_Common_floatVec_t

from Phyto.Common.shortVec import _Phyto_Common_shortVec_t

from dataclasses import dataclass
from dataclasses import field


@dataclass
class imageData:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::imageData``.
    """
    timeNbr: int = 0
    height: int = 0
    width: int = 0
    spp: int = 0
    imgformat: IMAGEFORMAT = IMAGEFORMAT.PMUNKNOWN
    imgDataType: IMAGEDATATYPE = IMAGEDATATYPE.IDTUNKNOWN
    cameraId: int = 0
    virtualCamParams: cameraParams = field(default_factory=cameraParams)
    boolPixels: list[bool] = field(default_factory=list)
    bytePixels: bytes = field(default_factory=bytes)
    shortPixels: list[int] = field(default_factory=list)
    floatPixels: list[float] = field(default_factory=list)

_Phyto_Common_imageData_t = IcePy.defineStruct(
    "::Phyto::Common::imageData",
    imageData,
    (),
    (
        ("timeNbr", (), IcePy._t_long),
        ("height", (), IcePy._t_int),
        ("width", (), IcePy._t_int),
        ("spp", (), IcePy._t_int),
        ("imgformat", (), _Phyto_Common_IMAGEFORMAT_t),
        ("imgDataType", (), _Phyto_Common_IMAGEDATATYPE_t),
        ("cameraId", (), IcePy._t_int),
        ("virtualCamParams", (), _Phyto_Common_cameraParams_t),
        ("boolPixels", (), _Phyto_Common_boolVec_t),
        ("bytePixels", (), _Phyto_Common_byteVec_t),
        ("shortPixels", (), _Phyto_Common_shortVec_t),
        ("floatPixels", (), _Phyto_Common_floatVec_t)
    ))

__all__ = ["imageData", "_Phyto_Common_imageData_t"]
