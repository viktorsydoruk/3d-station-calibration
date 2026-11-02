# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.treatment import _Phyto_Common_treatment_t

_Phyto_Common_treatmentVec_t = IcePy.defineSequence("::Phyto::Common::treatmentVec", (), _Phyto_Common_treatment_t)

__all__ = ["_Phyto_Common_treatmentVec_t"]
