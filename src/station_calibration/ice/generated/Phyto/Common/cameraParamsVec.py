# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.cameraParams import _Phyto_Common_cameraParams_t

_Phyto_Common_cameraParamsVec_t = IcePy.defineSequence("::Phyto::Common::cameraParamsVec", (), _Phyto_Common_cameraParams_t)

__all__ = ["_Phyto_Common_cameraParamsVec_t"]
