# Copyright (c) ZeroC, Inc.

# slice2py version 3.8.3

from __future__ import annotations
import IcePy

from CommonPhenoseeder.vecOfDoubles import _CommonPhenoseeder_vecOfDoubles_t

from Ice.Object import Object

from Ice.ObjectPrx import ObjectPrx
from Ice.ObjectPrx import checkedCast
from Ice.ObjectPrx import checkedCastAsync
from Ice.ObjectPrx import uncheckedCast

from Ice.OperationMode import OperationMode

from Phenoseeder.CalibrationPhenoseederIcing_forward import _Phenoseeder_CalibrationPhenoseederIcingPrx_t

from Phenoseeder.DoubleSeq import _Phenoseeder_DoubleSeq_t

from Phenoseeder.Point import _Phenoseeder_Point_t

from Phyto.Common.extrinsicParams import _Phyto_Common_extrinsicParams_t

from Phyto.Common.imageData import _Phyto_Common_imageData_t

from Phyto.Common.intrinsicParams import _Phyto_Common_intrinsicParams_t

from abc import ABC
from abc import abstractmethod

from typing import TYPE_CHECKING
from typing import overload

if TYPE_CHECKING:
    from Ice.Current import Current
    from Phenoseeder.Point import Point
    from Phyto.Common.extrinsicParams import extrinsicParams
    from Phyto.Common.imageData import imageData
    from Phyto.Common.intrinsicParams import intrinsicParams
    from collections.abc import Awaitable
    from collections.abc import Buffer
    from collections.abc import Sequence


class CalibrationPhenoseederIcingPrx(ObjectPrx):
    """
    Notes
    -----
        The Slice compiler generated this proxy class from Slice interface ``::Phenoseeder::CalibrationPhenoseederIcing``.
    """

    def calibrate(self, numberOfPoints: int, shutter: int, gain: int, ubV: int, vrV: int, offsetX: int, offsetY: int, HMin: int, HMax: int, SMin: int, SMax: int, VMin: int, VMax: int, minSizeObj: int, maxSizeObj: int, minSizeHoles: int, mask: imageData, h: int, w: int, c: float, z: float, centralPointX: float, centralPointY: float, radius: float, tool: int, context: dict[str, str] | None = None) -> list[float]:
        return CalibrationPhenoseederIcing._op_calibrate.invoke(self, ((numberOfPoints, shutter, gain, ubV, vrV, offsetX, offsetY, HMin, HMax, SMin, SMax, VMin, VMax, minSizeObj, maxSizeObj, minSizeHoles, mask, h, w, c, z, centralPointX, centralPointY, radius, tool), context))

    def calibrateAsync(self, numberOfPoints: int, shutter: int, gain: int, ubV: int, vrV: int, offsetX: int, offsetY: int, HMin: int, HMax: int, SMin: int, SMax: int, VMin: int, VMax: int, minSizeObj: int, maxSizeObj: int, minSizeHoles: int, mask: imageData, h: int, w: int, c: float, z: float, centralPointX: float, centralPointY: float, radius: float, tool: int, context: dict[str, str] | None = None) -> Awaitable[list[float]]:
        return CalibrationPhenoseederIcing._op_calibrate.invokeAsync(self, ((numberOfPoints, shutter, gain, ubV, vrV, offsetX, offsetY, HMin, HMax, SMin, SMax, VMin, VMax, minSizeObj, maxSizeObj, minSizeHoles, mask, h, w, c, z, centralPointX, centralPointY, radius, tool), context))

    def init(self, procedureId: int, configurationfilepath: str | None = None, context: dict[str, str] | None = None) -> str:
        return CalibrationPhenoseederIcing._op_init.invoke(self, ((procedureId, configurationfilepath), context))

    def initAsync(self, procedureId: int, configurationfilepath: str | None = None, context: dict[str, str] | None = None) -> Awaitable[str]:
        return CalibrationPhenoseederIcing._op_init.invokeAsync(self, ((procedureId, configurationfilepath), context))

    def addData(self, robotCoord: Point, image: imageData, context: dict[str, str] | None = None) -> None:
        return CalibrationPhenoseederIcing._op_addData.invoke(self, ((robotCoord, image), context))

    def addDataAsync(self, robotCoord: Point, image: imageData, context: dict[str, str] | None = None) -> Awaitable[None]:
        return CalibrationPhenoseederIcing._op_addData.invokeAsync(self, ((robotCoord, image), context))

    def isReady(self, context: dict[str, str] | None = None) -> bool:
        return CalibrationPhenoseederIcing._op_isReady.invoke(self, ((), context))

    def isReadyAsync(self, context: dict[str, str] | None = None) -> Awaitable[bool]:
        return CalibrationPhenoseederIcing._op_isReady.invokeAsync(self, ((), context))

    def getIntrinsic(self, context: dict[str, str] | None = None) -> tuple[intrinsicParams, list[float]]:
        return CalibrationPhenoseederIcing._op_getIntrinsic.invoke(self, ((), context))

    def getIntrinsicAsync(self, context: dict[str, str] | None = None) -> Awaitable[tuple[intrinsicParams, list[float]]]:
        return CalibrationPhenoseederIcing._op_getIntrinsic.invokeAsync(self, ((), context))

    def getExtrinsic(self, context: dict[str, str] | None = None) -> tuple[extrinsicParams, list[float]]:
        return CalibrationPhenoseederIcing._op_getExtrinsic.invoke(self, ((), context))

    def getExtrinsicAsync(self, context: dict[str, str] | None = None) -> Awaitable[tuple[extrinsicParams, list[float]]]:
        return CalibrationPhenoseederIcing._op_getExtrinsic.invokeAsync(self, ((), context))

    def getDistortion(self, context: dict[str, str] | None = None) -> tuple[list[float], list[float]]:
        return CalibrationPhenoseederIcing._op_getDistortion.invoke(self, ((), context))

    def getDistortionAsync(self, context: dict[str, str] | None = None) -> Awaitable[tuple[list[float], list[float]]]:
        return CalibrationPhenoseederIcing._op_getDistortion.invokeAsync(self, ((), context))

    def getOptimalNozzlePosition(self, context: dict[str, str] | None = None) -> Point:
        return CalibrationPhenoseederIcing._op_getOptimalNozzlePosition.invoke(self, ((), context))

    def getOptimalNozzlePositionAsync(self, context: dict[str, str] | None = None) -> Awaitable[Point]:
        return CalibrationPhenoseederIcing._op_getOptimalNozzlePosition.invokeAsync(self, ((), context))

    @staticmethod
    def checkedCast(
        proxy: ObjectPrx | None,
        facet: str | None = None,
        context: dict[str, str] | None = None
    ) -> CalibrationPhenoseederIcingPrx | None:
        return checkedCast(CalibrationPhenoseederIcingPrx, proxy, facet, context)

    @staticmethod
    def checkedCastAsync(
        proxy: ObjectPrx | None,
        facet: str | None = None,
        context: dict[str, str] | None = None
    ) -> Awaitable[CalibrationPhenoseederIcingPrx | None ]:
        return checkedCastAsync(CalibrationPhenoseederIcingPrx, proxy, facet, context)

    @overload
    @staticmethod
    def uncheckedCast(proxy: ObjectPrx, facet: str | None = None) -> CalibrationPhenoseederIcingPrx:
        ...

    @overload
    @staticmethod
    def uncheckedCast(proxy: None, facet: str | None = None) -> None:
        ...

    @staticmethod
    def uncheckedCast(proxy: ObjectPrx | None, facet: str | None = None) -> CalibrationPhenoseederIcingPrx | None:
        return uncheckedCast(CalibrationPhenoseederIcingPrx, proxy, facet)

    @staticmethod
    def ice_staticId() -> str:
        return "::Phenoseeder::CalibrationPhenoseederIcing"

IcePy.defineProxy("::Phenoseeder::CalibrationPhenoseederIcing", CalibrationPhenoseederIcingPrx)

class CalibrationPhenoseederIcing(Object, ABC):
    """
    Notes
    -----
        The Slice compiler generated this skeleton class from Slice interface ``::Phenoseeder::CalibrationPhenoseederIcing``.
    """

    _ice_ids: Sequence[str] = ("::Ice::Object", "::Phenoseeder::CalibrationPhenoseederIcing", )
    _op_calibrate: IcePy.Operation
    _op_init: IcePy.Operation
    _op_addData: IcePy.Operation
    _op_isReady: IcePy.Operation
    _op_getIntrinsic: IcePy.Operation
    _op_getExtrinsic: IcePy.Operation
    _op_getDistortion: IcePy.Operation
    _op_getOptimalNozzlePosition: IcePy.Operation

    @staticmethod
    def ice_staticId() -> str:
        return "::Phenoseeder::CalibrationPhenoseederIcing"

    @abstractmethod
    def calibrate(self, numberOfPoints: int, shutter: int, gain: int, ubV: int, vrV: int, offsetX: int, offsetY: int, HMin: int, HMax: int, SMin: int, SMax: int, VMin: int, VMax: int, minSizeObj: int, maxSizeObj: int, minSizeHoles: int, mask: imageData, h: int, w: int, c: float, z: float, centralPointX: float, centralPointY: float, radius: float, tool: int, current: Current) -> Sequence[float] | Buffer | Awaitable[Sequence[float] | Buffer]:
        pass

    @abstractmethod
    def init(self, procedureId: int, configurationfilepath: str | None, current: Current) -> str | Awaitable[str]:
        pass

    @abstractmethod
    def addData(self, robotCoord: Point, image: imageData, current: Current) -> None | Awaitable[None]:
        pass

    @abstractmethod
    def isReady(self, current: Current) -> bool | Awaitable[bool]:
        pass

    @abstractmethod
    def getIntrinsic(self, current: Current) -> tuple[intrinsicParams, Sequence[float] | Buffer] | Awaitable[tuple[intrinsicParams, Sequence[float] | Buffer]]:
        pass

    @abstractmethod
    def getExtrinsic(self, current: Current) -> tuple[extrinsicParams, Sequence[float] | Buffer] | Awaitable[tuple[extrinsicParams, Sequence[float] | Buffer]]:
        pass

    @abstractmethod
    def getDistortion(self, current: Current) -> tuple[Sequence[float] | Buffer, Sequence[float] | Buffer] | Awaitable[tuple[Sequence[float] | Buffer, Sequence[float] | Buffer]]:
        pass

    @abstractmethod
    def getOptimalNozzlePosition(self, current: Current) -> Point | Awaitable[Point]:
        pass

CalibrationPhenoseederIcing._op_calibrate = IcePy.Operation(
    "calibrate",
    "calibrate",
    OperationMode.Normal,
    None,
    (),
    (((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), _Phyto_Common_imageData_t, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_int, False, 0), ((), IcePy._t_double, False, 0), ((), IcePy._t_double, False, 0), ((), IcePy._t_double, False, 0), ((), IcePy._t_double, False, 0), ((), IcePy._t_double, False, 0), ((), IcePy._t_int, False, 0)),
    (((), _CommonPhenoseeder_vecOfDoubles_t, False, 0),),
    None,
    (),
    False)

CalibrationPhenoseederIcing._op_init = IcePy.Operation(
    "init",
    "init",
    OperationMode.Normal,
    None,
    (),
    (((), IcePy._t_int, False, 0), ((), IcePy._t_string, True, 1)),
    (),
    ((), IcePy._t_string, False, 0),
    (),
    False)

CalibrationPhenoseederIcing._op_addData = IcePy.Operation(
    "addData",
    "addData",
    OperationMode.Normal,
    None,
    (),
    (((), _Phenoseeder_Point_t, False, 0), ((), _Phyto_Common_imageData_t, False, 0)),
    (),
    None,
    (),
    False)

CalibrationPhenoseederIcing._op_isReady = IcePy.Operation(
    "isReady",
    "isReady",
    OperationMode.Normal,
    None,
    (),
    (),
    (),
    ((), IcePy._t_bool, False, 0),
    (),
    False)

CalibrationPhenoseederIcing._op_getIntrinsic = IcePy.Operation(
    "getIntrinsic",
    "getIntrinsic",
    OperationMode.Normal,
    None,
    (),
    (),
    (((), _Phyto_Common_intrinsicParams_t, False, 0), ((), _Phenoseeder_DoubleSeq_t, False, 0)),
    None,
    (),
    False)

CalibrationPhenoseederIcing._op_getExtrinsic = IcePy.Operation(
    "getExtrinsic",
    "getExtrinsic",
    OperationMode.Normal,
    None,
    (),
    (),
    (((), _Phyto_Common_extrinsicParams_t, False, 0), ((), _Phenoseeder_DoubleSeq_t, False, 0)),
    None,
    (),
    False)

CalibrationPhenoseederIcing._op_getDistortion = IcePy.Operation(
    "getDistortion",
    "getDistortion",
    OperationMode.Normal,
    None,
    (),
    (),
    (((), _Phenoseeder_DoubleSeq_t, False, 0), ((), _Phenoseeder_DoubleSeq_t, False, 0)),
    None,
    (),
    False)

CalibrationPhenoseederIcing._op_getOptimalNozzlePosition = IcePy.Operation(
    "getOptimalNozzlePosition",
    "getOptimalNozzlePosition",
    OperationMode.Normal,
    None,
    (),
    (),
    (((), _Phenoseeder_Point_t, False, 0),),
    None,
    (),
    False)

__all__ = ["CalibrationPhenoseederIcing", "CalibrationPhenoseederIcingPrx", "_Phenoseeder_CalibrationPhenoseederIcingPrx_t"]
