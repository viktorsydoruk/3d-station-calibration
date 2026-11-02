# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.intrinsicParams import _Phyto_Common_intrinsicParams_t

_Phyto_Common_intrinsicParamsVec_t = IcePy.defineSequence("::Phyto::Common::intrinsicParamsVec", (), _Phyto_Common_intrinsicParams_t)

__all__ = ["_Phyto_Common_intrinsicParamsVec_t"]
