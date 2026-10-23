# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.ByteSeq import _Phyto_Common_ByteSeq_t

from dataclasses import dataclass
from dataclasses import field


@dataclass
class imageData:
    """
    Notes
    -----
        The Slice compiler generated this dataclass from Slice struct ``::Phyto::Common::imageData``.
    """
    data: bytes = field(default_factory=bytes)
    width: int = 0
    height: int = 0
    channels: int = 0

_Phyto_Common_imageData_t = IcePy.defineStruct(
    "::Phyto::Common::imageData",
    imageData,
    (),
    (
        ("data", (), _Phyto_Common_ByteSeq_t),
        ("width", (), IcePy._t_int),
        ("height", (), IcePy._t_int),
        ("channels", (), IcePy._t_int)
    ))

__all__ = ["imageData", "_Phyto_Common_imageData_t"]
