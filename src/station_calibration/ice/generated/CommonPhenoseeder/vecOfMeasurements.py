# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.Measurement import _CommonPhenoseeder_Measurement_t

_CommonPhenoseeder_vecOfMeasurements_t = IcePy.defineSequence("::CommonPhenoseeder::vecOfMeasurements", (), _CommonPhenoseeder_Measurement_t)

__all__ = ["_CommonPhenoseeder_vecOfMeasurements_t"]
