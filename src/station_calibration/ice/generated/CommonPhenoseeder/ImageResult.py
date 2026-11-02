# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from dataclasses import dataclass


@dataclass(order=True, unsafe_hash=True)
class ImageResult:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::CommonPhenoseeder::ImageResult``.
    """
    FileName: str = ""
    ImageTypeId: int = 0
    Description: str = ""

_CommonPhenoseeder_ImageResult_t = IcePy.defineStruct(
    "::CommonPhenoseeder::ImageResult",
    ImageResult,
    (),
    (
        ("FileName", (), IcePy._t_string),
        ("ImageTypeId", (), IcePy._t_int),
        ("Description", (), IcePy._t_string)
    ))

__all__ = ["ImageResult", "_CommonPhenoseeder_ImageResult_t"]
