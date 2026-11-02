# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Image loading and decoding helpers."""

__all__ = [
    "load_image",
    "decode_image",
    "split_image",
]

from pathlib import Path

import cv2
import numpy as np


def split_image(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
        Convert a raw Bayer or color image into gray- and color-scale variants.

        Two-dimensional images are interpreted as raw Bayer frames, matching the
        calibration camera. Three- and four-channel images are interpreted as BGR
        and BGRA respectively.
    """
    if image is None:
        raise ValueError("Image could not be loaded")

    if image.ndim == 2:
        image_color = cv2.cvtColor(image, cv2.COLOR_BAYER_BG2BGR)
        image_gray = cv2.cvtColor(image, cv2.COLOR_BAYER_BG2GRAY)
    elif image.ndim == 3 and image.shape[2] == 3:
        image_color = image
        image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 3 and image.shape[2] == 4:
        image_color = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        image_gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError(f"Unsupported image shape: {image.shape}")

    return image_gray, image_color


def load_image(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load an image and return gray- and color-scale variants of it."""
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Could not read image file: {image_path}")
    return split_image(image)


def decode_image(image_bytes: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Decode encoded image bytes (for example TIFF or PNG) into gray- and color-scale variants."""
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")

    image = cv2.imdecode(
        np.frombuffer(image_bytes, dtype=np.uint8),
        cv2.IMREAD_UNCHANGED,
    )
    if image is None:
        raise ValueError("Could not decode image bytes")
    return split_image(image)
