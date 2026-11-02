# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.PotAllocation import _CommonPhenoseeder_PotAllocation_t

_CommonPhenoseeder_trayAllocation_t = IcePy.defineSequence("::CommonPhenoseeder::trayAllocation", (), _CommonPhenoseeder_PotAllocation_t)

__all__ = ["_CommonPhenoseeder_trayAllocation_t"]
