# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Debug-image rendering for vision analysis."""

__all__ = [
    "debug_images_storing",
]

from pathlib import Path

import cv2
import numpy as np


def debug_images_storing(filename: Path,
                         result: np.ndarray,
                         **kwargs) -> None:
    x_c_pos = kwargs.get('x_c_pos', None)
    y_c_pos = kwargs.get('y_c_pos', None)
    radius = kwargs.get('radius', None)
    target = Path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)

    canvas = result
    if (
        x_c_pos is not None
        and y_c_pos is not None
        and radius is not None
        and np.isfinite(x_c_pos)
        and np.isfinite(y_c_pos)
        and np.isfinite(radius)
        and radius >= 0
    ):
        # Callers may hand us a read-only view (for example a frame received
        # through Ice). Never mutate their array while drawing diagnostics.
        canvas = np.array(result, copy=True)
        center = (int(round(float(x_c_pos))), int(round(float(y_c_pos))))
        cv2.circle(canvas, center, int(round(float(radius))), (0, 255, 0), 2)
        cv2.circle(canvas, center, 3, (0, 0, 255), -1)
    cv2.imwrite(str(target), canvas)


def _store_debug_image(debug_imagefile: Path | None,
                       image_color: np.ndarray | None,
                       **kwargs) -> None:
    """Store a debug image when both a target and a color image are available."""
    if debug_imagefile is None or image_color is None:
        return
    debug_images_storing(debug_imagefile, image_color, **kwargs)
