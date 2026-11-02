# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.leaf import _Phyto_Common_leaf_t

_Phyto_Common_leaveslist_t = IcePy.defineSequence("::Phyto::Common::leaveslist", (), _Phyto_Common_leaf_t)

__all__ = ["_Phyto_Common_leaveslist_t"]
