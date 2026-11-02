# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.Point import _CommonPhenoseeder_Point_t

_CommonPhenoseeder_vecOfPoints_t = IcePy.defineSequence("::CommonPhenoseeder::vecOfPoints", (), _CommonPhenoseeder_Point_t)

__all__ = ["_CommonPhenoseeder_vecOfPoints_t"]
