# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass
class treatment:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::treatment``.
    """
    timestamp: int = 0
    value: float = 0.0

_Phyto_Common_treatment_t = IcePy.defineStruct(
    "::Phyto::Common::treatment",
    treatment,
    (),
    (
        ("timestamp", (), IcePy._t_long),
        ("value", (), IcePy._t_double)
    ))

__all__ = ["treatment", "_Phyto_Common_treatment_t"]
