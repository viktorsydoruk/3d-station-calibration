# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Deprecated compatibility shim for :mod:`station_calibration.vision`."""

__all__ = [
    "load_image",
    "decode_image",
    "analyze_image",
    "analyze_image_bytes",
    "analyze_images",
    "get_sphere_centers_and_blur_sigmas",
    "get_radius_outlier_mask",
    "filtering_data_by_radius",
    "adjust_image_center_points",
    "SphereObservation",
    "ImageAnalysisResult",
]

from .vision import (
    ImageAnalysisResult,
    SphereObservation,
    adjust_image_center_points,
    analyze_image,
    analyze_image_bytes,
    analyze_images,
    decode_image,
    filtering_data_by_radius,
    get_radius_outlier_mask,
    get_sphere_centers_and_blur_sigmas,
    load_image,
)
from .vision.debug import _store_debug_image, debug_images_storing
from .vision.detection import (
    estimate_direction,
    find_the_sphere_on_mask,
    fit_circle,
    gaussian_fit,
    gaussian_model,
    get_bg_value,
    get_blur_sigma,
    get_cut_sphere_mask,
    get_forground_mask,
    smooth_1D_array,
)
from .vision.io import _split_image
