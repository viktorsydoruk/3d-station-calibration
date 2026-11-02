# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from Phyto.Common.imageData import _Phyto_Common_imageData_t

_Phyto_Common_imageFrames_t = IcePy.defineSequence("::Phyto::Common::imageFrames", (), _Phyto_Common_imageData_t)

__all__ = ["_Phyto_Common_imageFrames_t"]
