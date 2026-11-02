# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.plantgraph import _Phyto_Common_plantgraph_t

_Phyto_Common_graphlist_t = IcePy.defineSequence("::Phyto::Common::graphlist", (), _Phyto_Common_plantgraph_t)

__all__ = ["_Phyto_Common_graphlist_t"]
