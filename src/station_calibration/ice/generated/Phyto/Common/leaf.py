# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass(order=True, unsafe_hash=True)
class leaf:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::leaf``.
    """
    no: int = 0
    size: int = 0

_Phyto_Common_leaf_t = IcePy.defineStruct(
    "::Phyto::Common::leaf",
    leaf,
    (),
    (
        ("no", (), IcePy._t_int),
        ("size", (), IcePy._t_int)
    ))

__all__ = ["leaf", "_Phyto_Common_leaf_t"]
