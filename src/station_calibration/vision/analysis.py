# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Single-image and batch sphere analysis."""

__all__ = [
    "analyze_image",
    "analyze_image_array",
    "analyze_image_bytes",
    "get_radius_outlier_mask",
    "filtering_data_by_radius",
    "analyze_images",
    "get_sphere_centers_and_blur_sigmas",
]

import time
from pathlib import Path

import numpy as np

from ..debug import DebugInfo
from .debug import _store_debug_image, debug_images_storing
from .detection import (
    estimate_direction,
    find_the_sphere_on_mask,
    get_bg_value,
    get_blur_sigma,
    get_forground_mask,
)
from .io import decode_image, load_image, split_image
from .models import ImageAnalysisResult, SphereObservation


def analyze_image(image_gray: np.ndarray,
                  image_color: np.ndarray | None = None,
                  *,
                  bg_height_px: int = 300,
                  bg_color_est_perc: float = 99.9,
                  fixed_bg_threshold: float = 0,
                  n_mov_aver: int = 11,
                  sphere_center_to_nozzle_part: float = 0.3,
                  min_bg_pixels_on_edges: int = 5,
                  blur_est_border_thickness: int = 2,
                  print_debug: DebugInfo = DebugInfo(),
                  image_index: int | None = None,
                  debug_imagefile: Path | None = None,
                  store_debug_images: bool = False,
                  estimate_center_covariance: bool = True,
                  ) -> ImageAnalysisResult:
    """
        Analyze one image and extract the sphere center, radius, edge blur and nozzle direction.

        This function does not read from the filesystem. Optional debug images can be written
        when both ``debug_imagefile`` and ``image_color`` are given.

    :param image_gray: gray-scale image
    :param image_color: color image used only for optional debug images
    :param bg_height_px: estimated background height at the bottom or at the top of the image
    :param bg_color_est_perc: percentile to estimate the background color
    :param fixed_bg_threshold: fixed background threshold (0 means automatic estimation)
    :param n_mov_aver: number of moving average pixels to smooth intermediate data
    :param sphere_center_to_nozzle_part: part of the sphere between center and nozzle
    :param min_bg_pixels_on_edges: min number of background pixels at image edges
    :param blur_est_border_thickness: border thickness for blur estimation
    :param print_debug: prints intermediate information if enabled
    :param image_index: optional image number used in debug output
    :param debug_imagefile: optional path for a debug image
    :param store_debug_images: whether successful results should also store a debug image
    :param estimate_center_covariance: whether to propagate the circle-fit centre covariance
    :return: analysis result with an observation or a rejection reason
    """
    image_shape = (int(image_gray.shape[0]), int(image_gray.shape[1]))
    starting_time = time.perf_counter()

    # getting the direction (1 - nozzle on the top, -1 - nozzle at the bottom, 0 - undefined)
    direction = estimate_direction(image_gray, bg_height_px=bg_height_px // 2)
    image_label = f"{image_index:>03d} image" if image_index is not None else "image"
    print_debug(f"{image_label} - direction: {direction:+}, ", end="")

    def rejected(reason: str, **debug_kwargs) -> ImageAnalysisResult:
        _store_debug_image(debug_imagefile, image_color, **debug_kwargs)
        print_debug(reason)
        return ImageAnalysisResult(None, direction, image_shape, reason)

    # if direction is undefined the measurement should be skipped
    if direction == 0:
        return rejected("direction is undefined")

    bg_thr = fixed_bg_threshold
    if bg_thr == 0:
        # getting the highest background value (allowing only a few pixels to be higher)
        bg_thr = get_bg_value(
            image_gray,
            bg_height_px=bg_height_px,
            perc=bg_color_est_perc,
            direction=direction,
        )
    print_debug(f"BG_thr: {bg_thr:0.1f}, ", end="")

    # getting foreground mask for the nozzle with a ball only (removing the other islands)
    forground_mask = get_forground_mask(image_gray, bg_thr)

    # searching the sphere on the foreground mask
    sphere_params = find_the_sphere_on_mask(
        forground_mask,
        n_mov_aver=n_mov_aver,
        sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
        direction=direction,
        min_bg_pixels_on_edges=min_bg_pixels_on_edges,
        return_covariance=estimate_center_covariance,
    )

    if sphere_params is None:
        return rejected("sphere is not found or out of FOV")

    if len(sphere_params) == 4:
        x_c_pos, y_c_pos, radius, center_covariance = sphere_params
    else:
        x_c_pos, y_c_pos, radius = sphere_params
        center_covariance = None

    # getting the sigmas of edge blurring
    sigma = get_blur_sigma(
        image_gray,
        x_c_pos,
        y_c_pos,
        radius + min_bg_pixels_on_edges,
        sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
        direction=direction,
        border_thickness=blur_est_border_thickness,
    )

    if sigma is None:
        return rejected(
            "border sigma cannot be estimated",
            x_c_pos=x_c_pos,
            y_c_pos=y_c_pos,
            radius=radius,
        )

    print_debug(f"sphere center: ({x_c_pos:>07.2f}, {y_c_pos:>07.2f}), radius: {radius:0.2f}, border sigma: {sigma:>5.2f} "
                f"time: {time.perf_counter() - starting_time:0.2f} s.")

    if store_debug_images:
        _store_debug_image(
            debug_imagefile,
            image_color,
            x_c_pos=x_c_pos,
            y_c_pos=y_c_pos,
            radius=radius,
        )

    return ImageAnalysisResult(
        SphereObservation(
            x_c_pos,
            y_c_pos,
            radius,
            sigma,
            center_covariance=center_covariance,
        ),
        direction,
        image_shape,
    )


def analyze_image_array(image: np.ndarray, **kwargs) -> ImageAnalysisResult:
    """Analyze a raw NumPy image array.

    Two-dimensional arrays are interpreted as raw Bayer frames, matching the
    calibration camera. Three- and four-channel arrays are interpreted as BGR
    and BGRA respectively.
    """
    image_gray, image_color = split_image(image)
    return analyze_image(image_gray, image_color, **kwargs)


def analyze_image_bytes(image_bytes: bytes, **kwargs) -> ImageAnalysisResult:
    """Decode image bytes and analyze the resulting image."""
    image_gray, image_color = decode_image(image_bytes)
    return analyze_image(image_gray, image_color, **kwargs)


def get_radius_outlier_mask(radii: np.ndarray,
                            sigmas: np.ndarray) -> np.ndarray:
    """Return a mask of radii that are outside 2.5 standard deviations."""
    std_radii = np.nanstd(radii)
    mean_radius = np.nanmean(radii)
    return (np.abs(radii - mean_radius) > 2.5*std_radii) & (~np.isnan(sigmas))


def filtering_data_by_radius(image_filenames: list[Path],
                             sphere_centers: np.ndarray,
                             sigmas: np.ndarray,
                             radii: np.ndarray,
                             print_debug: DebugInfo = DebugInfo(),
                             debug_folder: Path | None = None) -> None:
    """
        Filtering data by radius. If estimated sphere radius is out of statistics the values are replaced with np.nan
    :param image_filenames:
    :param sphere_centers:
    :param sigmas:
    :param radii:
    :param print_debug:
    :param debug_folder:
    :return:
    """
    # filtering by radius
    bad_mask = get_radius_outlier_mask(radii, sigmas)
    if print_debug.debug and debug_folder is not None:
        for each_arg_bad_est in np.arange(len(radii))[bad_mask]:
            try:
                _, image_color = load_image(image_filenames[each_arg_bad_est])
                debug_images_storing(
                    debug_folder / f"result{each_arg_bad_est:>04d}.png",
                    image_color,
                    x_c_pos=sphere_centers[each_arg_bad_est, 0],
                    y_c_pos=sphere_centers[each_arg_bad_est, 1],
                    radius=radii[each_arg_bad_est]
                )
            except MemoryError:
                raise
            except Exception as exc:
                print_debug(
                    f"debug image failed for {image_filenames[each_arg_bad_est]}: "
                    f"{type(exc).__name__}: {exc}"
                )
    sigmas[bad_mask] = np.nan
    radii[bad_mask] = np.nan


def analyze_images(image_filenames: list[Path],
                   bg_height_px: int = 300,
                   bg_color_est_perc: float = 99.9,
                   fixed_bg_threshold: float = 0,
                   n_mov_aver: int = 11,
                   sphere_center_to_nozzle_part: float = 0.3,
                   min_bg_pixels_on_edges: int = 5,
                   blur_est_border_thickness: int = 2,
                   print_debug: DebugInfo = DebugInfo(),
                   store_debug_images: bool = False,
                   debug_folder: Path | None = None,
                   estimate_center_covariance: bool = True,
                   ) -> list[ImageAnalysisResult]:
    """Analyze a list of image files one by one and return each analysis result."""
    analyses = []
    for i, each_image in enumerate(image_filenames):
        # file to store debug image
        debug_imagefile = (
            None if debug_folder is None else debug_folder / f"result{i:>04d}.png"
        )
        image_shape = (0, 0)

        try:
            # loading the image
            image_gray, image_color = load_image(each_image)
            image_shape = (int(image_gray.shape[0]), int(image_gray.shape[1]))
            analysis = analyze_image(
                image_gray,
                image_color,
                bg_height_px=bg_height_px,
                bg_color_est_perc=bg_color_est_perc,
                fixed_bg_threshold=fixed_bg_threshold,
                n_mov_aver=n_mov_aver,
                sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
                min_bg_pixels_on_edges=min_bg_pixels_on_edges,
                blur_est_border_thickness=blur_est_border_thickness,
                print_debug=print_debug,
                image_index=i,
                debug_imagefile=debug_imagefile,
                store_debug_images=store_debug_images,
                estimate_center_covariance=estimate_center_covariance,
            )
        except MemoryError:
            raise
        except Exception as exc:
            # A corrupt or unsupported frame must not abort the entire folder.
            # Keep a rejection in its position so filenames and observations
            # stay aligned.
            print_debug(
                f"image analysis failed for {each_image}: "
                f"{type(exc).__name__}: {exc}"
            )
            analysis = ImageAnalysisResult(
                observation=None,
                direction=0,
                image_shape=image_shape,
                reason=f"image analysis failed: {type(exc).__name__}: {exc}",
            )
        analyses.append(analysis)

    return analyses


def get_sphere_centers_and_blur_sigmas(image_filenames: list[Path],
                                       bg_height_px: int = 300,
                                       bg_color_est_perc: float = 99.9,
                                       fixed_bg_threshold: float = 0,
                                       n_mov_aver: int = 11,
                                       sphere_center_to_nozzle_part: float = 0.3,
                                       min_bg_pixels_on_edges: int = 5,
                                       blur_est_border_thickness: int = 2,
                                       print_debug: DebugInfo = DebugInfo(),
                                       store_debug_images: bool = False,
                                       debug_folder: Path | None = None,
                                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
        Getting found sphere parameters and bluring sigma at the border of the sphere
    :param image_filenames: list of the paths to images
    :param bg_height_px: estimated background height at the bottom or at the top of each image
    :param bg_color_est_perc: percentile to estimate the background color
    :param fixed_bg_threshold: fixed background threshold (if 0 the threshold will be automatically calculated)
    :param n_mov_aver: number of moving average pixels to smooth the intermediate data
    :param sphere_center_to_nozzle_part: part of the sphere between its center and the nozzle that should be taken into account
    :param min_bg_pixels_on_edges: min number of pixels between the edge of the sphere and each edge of the image
    :param blur_est_border_thickness: border thickness of each step along the radius to estimate blurring sigma
    :param print_debug: print debug information if needed
    :param store_debug_images: whether to store the debug images
    :param debug_folder: folder to store debug information
    :return: sphere centers, border sigmas, radii, image sizes and nozzle directions
    """
    analyses = analyze_images(
        image_filenames,
        bg_height_px=bg_height_px,
        bg_color_est_perc=bg_color_est_perc,
        fixed_bg_threshold=fixed_bg_threshold,
        n_mov_aver=n_mov_aver,
        sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
        min_bg_pixels_on_edges=min_bg_pixels_on_edges,
        blur_est_border_thickness=blur_est_border_thickness,
        print_debug=print_debug,
        store_debug_images=store_debug_images,
        debug_folder=debug_folder,
    )

    sphere_centers_list: list[list[float]] = []
    border_sigmas_list: list[float] = []
    radii_list: list[float] = []
    image_sizes_list: list[tuple[int, int]] = []
    all_directions_list: list[int] = []

    for analysis in analyses:
        image_sizes_list.append(analysis.image_shape)
        all_directions_list.append(analysis.direction)

        if analysis.observation is None:
            sphere_centers_list.append([np.nan, np.nan])
            border_sigmas_list.append(np.nan)
            radii_list.append(np.nan)
        else:
            sphere_centers_list.append([analysis.observation.x, analysis.observation.y])
            border_sigmas_list.append(analysis.observation.sigma)
            radii_list.append(analysis.observation.radius)

    sphere_centers = np.array(sphere_centers_list, dtype=np.float64)
    border_sigmas = np.array(border_sigmas_list, dtype=np.float64)
    radii = np.array(radii_list, dtype=np.float64)
    image_sizes = np.array(image_sizes_list, dtype=np.float64)
    all_directions = np.array(all_directions_list, dtype=np.int8)

    # filtering the data that has bad radius estimation
    filtering_data_by_radius(
        image_filenames,
        sphere_centers,
        border_sigmas,
        radii,
        print_debug=print_debug,
        debug_folder=debug_folder,
    )

    return sphere_centers, border_sigmas, radii, image_sizes, all_directions
