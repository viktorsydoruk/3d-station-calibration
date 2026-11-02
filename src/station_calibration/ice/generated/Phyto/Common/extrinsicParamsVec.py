# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.extrinsicParams import _Phyto_Common_extrinsicParams_t

_Phyto_Common_extrinsicParamsVec_t = IcePy.defineSequence("::Phyto::Common::extrinsicParamsVec", (), _Phyto_Common_extrinsicParams_t)

__all__ = ["_Phyto_Common_extrinsicParamsVec_t"]
