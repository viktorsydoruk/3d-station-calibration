# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from enum import Enum

class IMAGEFORMAT(Enum):
    """
    Notes
    -----
        The Slice compiler generated this enum class from Slice enumeration ``::Phyto::Common::IMAGEFORMAT``.
    """

    PMUNKNOWN = 0

    PMBW = 1

    PMRGB = 2

    PMBGR = 3

    PMBGGR = 4

    PMRGGB = 5

    PMGRBG = 6

    PMGBRG = 7

    PMHSV = 8

    PMTHERMO = 9

    PMDISPARITY = 10

    PMDEPTH = 11

    PMSEGMENTATION = 12

    PMOPTICALFLOW = 13

    PMDENSEDISPARITY = 14

    PMGRAPH = 15

    PMYUV = 16

    PM3DIMAGE = 17

_Phyto_Common_IMAGEFORMAT_t = IcePy.defineEnum(
    "::Phyto::Common::IMAGEFORMAT",
    IMAGEFORMAT,
    (),
    {
        0: IMAGEFORMAT.PMUNKNOWN,
        1: IMAGEFORMAT.PMBW,
        2: IMAGEFORMAT.PMRGB,
        3: IMAGEFORMAT.PMBGR,
        4: IMAGEFORMAT.PMBGGR,
        5: IMAGEFORMAT.PMRGGB,
        6: IMAGEFORMAT.PMGRBG,
        7: IMAGEFORMAT.PMGBRG,
        8: IMAGEFORMAT.PMHSV,
        9: IMAGEFORMAT.PMTHERMO,
        10: IMAGEFORMAT.PMDISPARITY,
        11: IMAGEFORMAT.PMDEPTH,
        12: IMAGEFORMAT.PMSEGMENTATION,
        13: IMAGEFORMAT.PMOPTICALFLOW,
        14: IMAGEFORMAT.PMDENSEDISPARITY,
        15: IMAGEFORMAT.PMGRAPH,
        16: IMAGEFORMAT.PMYUV,
        17: IMAGEFORMAT.PM3DIMAGE,
    }
)

__all__ = ["IMAGEFORMAT", "_Phyto_Common_IMAGEFORMAT_t"]
