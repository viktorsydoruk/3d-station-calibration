# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.ImageResult import _CommonPhenoseeder_ImageResult_t

_CommonPhenoseeder_vecOfImageResults_t = IcePy.defineSequence("::CommonPhenoseeder::vecOfImageResults", (), _CommonPhenoseeder_ImageResult_t)

__all__ = ["_CommonPhenoseeder_vecOfImageResults_t"]
