# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.ENVIRONMENTPARAMETER import _Phyto_Common_ENVIRONMENTPARAMETER_t

_Phyto_Common_environmentInfo_t = IcePy.defineDictionary("::Phyto::Common::environmentInfo", (), _Phyto_Common_ENVIRONMENTPARAMETER_t, IcePy._t_double)

__all__ = ["_Phyto_Common_environmentInfo_t"]
