# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Conversion between NumPy frames and the production ``Phyto::Common::imageData``.

The shared Ice contract transports raw camera frames rather than encoded image
files. ``imageData`` carries exactly one of ``boolPixels``, ``bytePixels``,
``shortPixels``, or ``floatPixels`` together with ``height``, ``width``, and
``spp``. These helpers keep that mapping in one place for the client and the
servant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import cv2
import numpy as np

from ._generated import ensure_generated_on_path

ensure_generated_on_path()

from Phyto.Common import (  # noqa: E402
    IMAGEDATATYPE,
    IMAGEFORMAT,
    imageData,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "array_from_image_data",
    "decode_image",
    "image_data_from_array",
]

# Dtype -> (imageData field, IMAGEDATATYPE). The field order is the fallback
# used when a peer sends IDTUNKNOWN but still fills exactly one vector.
_PIXEL_FIELDS: tuple[tuple[str, type[np.generic], IMAGEDATATYPE], ...] = (
    ("bytePixels", np.uint8, IMAGEDATATYPE.IDTBYTE),
    ("boolPixels", np.bool_, IMAGEDATATYPE.IDTBOOL),
    ("shortPixels", np.int16, IMAGEDATATYPE.IDTSHORT),
    ("floatPixels", np.float32, IMAGEDATATYPE.IDTFLOAT),
)


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode encoded image bytes (TIFF, PNG, ...) into a NumPy frame."""
    if not image_bytes:
        raise ValueError("image bytes must not be empty")
    image = cv2.imdecode(
        np.frombuffer(image_bytes, dtype=np.uint8),
        cv2.IMREAD_UNCHANGED,
    )
    if image is None:
        raise ValueError("could not decode image bytes")
    return image


def image_data_from_array(image: np.ndarray,
                          *,
                          imgformat: IMAGEFORMAT | None = None) -> imageData:
    """Build a production ``imageData`` from a raw NumPy frame.

    Two-dimensional frames are treated as single-sample BG Bayer frames and
    three- or four-channel frames as colour frames, matching
    :func:`station_calibration.vision.split_image`.
    """
    array = np.asarray(image)
    if array.ndim == 2:
        height, width = array.shape
        spp = 1
        default_format = IMAGEFORMAT.PMBGGR
    elif array.ndim == 3 and array.shape[2] in (3, 4):
        height, width, spp = array.shape
        default_format = IMAGEFORMAT.PMBGR
    else:
        raise ValueError(f"unsupported image shape: {array.shape}")

    field, dtype, data_type = _wire_pixels(array)
    values = np.ascontiguousarray(array).reshape(-1).astype(dtype, copy=False)
    payload: dict[str, object] = {
        "height": int(height),
        "width": int(width),
        "spp": int(spp),
        "imgformat": default_format if imgformat is None else imgformat,
        "imgDataType": data_type,
    }
    if field == "bytePixels":
        payload[field] = values.tobytes()
    else:
        payload[field] = values.tolist()
    return imageData(**payload)


def array_from_image_data(image: imageData) -> np.ndarray:
    """Extract a raw NumPy frame from a production ``imageData`` value."""
    height = int(image.height)
    width = int(image.width)
    spp = int(image.spp) or 1
    if height <= 0 or width <= 0:
        raise ValueError(
            "imageData.height and imageData.width must be positive "
            f"(got {height}x{width})"
        )

    field, dtype = _select_pixels(image)
    raw = getattr(image, field)
    if field == "bytePixels":
        values = np.frombuffer(bytes(raw), dtype=np.uint8)
    else:
        values = np.asarray(raw, dtype=dtype)
    expected = height * width * spp
    if values.size != expected:
        raise ValueError(
            f"imageData.{field} has {values.size} values; "
            f"expected {expected} for {height}x{width}x{spp}"
        )

    shape = (height, width) if spp == 1 else (height, width, spp)
    return values.reshape(shape)


def _wire_pixels(array: np.ndarray) -> tuple[str, type[np.generic], IMAGEDATATYPE]:
    """Return the wire field, numpy dtype, and Slice data type for ``array``."""
    if array.dtype == np.uint8:
        return "bytePixels", np.uint8, IMAGEDATATYPE.IDTBYTE
    if array.dtype == np.bool_:
        return "boolPixels", np.bool_, IMAGEDATATYPE.IDTBOOL
    if array.dtype == np.int16:
        return "shortPixels", np.int16, IMAGEDATATYPE.IDTSHORT
    if array.dtype == np.uint16:
        if array.size and int(array.max()) > np.iinfo(np.int16).max:
            raise ValueError("uint16 image values exceed the signed 16-bit Ice range")
        return "shortPixels", np.int16, IMAGEDATATYPE.IDTSHORT
    if array.dtype in (np.float32, np.float64):
        return "floatPixels", np.float32, IMAGEDATATYPE.IDTFLOAT
    raise TypeError(f"unsupported image dtype: {array.dtype}")


def _select_pixels(image: imageData) -> tuple[str, type[np.generic]]:
    """Return the populated pixel vector and its numpy dtype."""
    by_data_type = {
        data_type: (field, dtype)
        for field, dtype, data_type in _PIXEL_FIELDS
    }
    selected = by_data_type.get(image.imgDataType)
    if selected is not None:
        field, dtype = selected
        if _is_populated(image, field):
            return field, dtype

    for field, dtype, _data_type in _PIXEL_FIELDS:
        if _is_populated(image, field):
            return field, dtype

    raise ValueError(
        "imageData does not contain any pixel data "
        "(boolPixels, bytePixels, shortPixels, or floatPixels)"
    )


def _is_populated(image: imageData, field: str) -> bool:
    values: Iterable[object] = getattr(image, field)
    return len(values) > 0
