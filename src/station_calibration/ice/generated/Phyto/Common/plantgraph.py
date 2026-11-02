# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.leaveslist import _Phyto_Common_leaveslist_t

from Phyto.Common.treatmentVec import _Phyto_Common_treatmentVec_t

from dataclasses import dataclass
from dataclasses import field

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Phyto.Common.leaf import leaf
    from Phyto.Common.treatment import treatment


@dataclass
class plantgraph:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::plantgraph``.
    """
    plantID: int = 0
    timeNbr: int = 0
    nodes: list[leaf] = field(default_factory=list)
    water: list[treatment] = field(default_factory=list)

_Phyto_Common_plantgraph_t = IcePy.defineStruct(
    "::Phyto::Common::plantgraph",
    plantgraph,
    (),
    (
        ("plantID", (), IcePy._t_long),
        ("timeNbr", (), IcePy._t_long),
        ("nodes", (), _Phyto_Common_leaveslist_t),
        ("water", (), _Phyto_Common_treatmentVec_t)
    ))

__all__ = ["plantgraph", "_Phyto_Common_plantgraph_t"]
