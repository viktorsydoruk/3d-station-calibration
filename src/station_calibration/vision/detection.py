# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Low-level sphere detection and edge-blur estimation."""

__all__ = [
    "get_bg_value",
    "estimate_direction",
    "get_forground_mask",
    "smooth_1D_array",
    "fit_circle",
    "find_the_sphere_on_mask",
    "get_cut_sphere_mask",
    "gaussian_model",
    "gaussian_fit",
    "get_blur_sigma",
]

import cv2
import numpy as np
from scipy.optimize import curve_fit


def get_bg_value(image_gray: np.ndarray,
                 bg_height_px: int = 300,
                 perc: float = 99.9,
                 direction: int = 1,
                 start_from: int = 10) -> int:
    """
        Get background intensity from image
    :param image_gray: gray-scale image
    :param bg_height_px: background height in pixels from the bottom of the image
    :param perc: percentile of background intensity
    :param direction: direction for calculations
    :param start_from: starting arg for estimation
    :return:
    """
    bg_std = []
    for i in range(start_from, bg_height_px+1, 1):
        bg_std.append(np.std(image_gray[-i:] if direction == 1 else image_gray[:i]))
    sel_arg = np.argmin(bg_std) + start_from
    values = image_gray[-sel_arg:] if direction == 1 else image_gray[:sel_arg]
    return np.percentile(values, perc)


def estimate_direction(image_gray: np.ndarray,
                       bg_height_px: int = 300) -> int:
    """
        Automatic estimation of the direction where the head with nozzle is comming from
        1 - comming from top of the image (at the bottom is only background)
        -1 - comming from the bottom of the image
        0 - undefined
    :param image_gray: gray-scale image
    :param bg_height_px: background height in pixels from the bottom or from the top of the image
    :return: either -1, or 0, or 1
    """
    bot_data = image_gray[-bg_height_px:]
    top_data = image_gray[:bg_height_px]
    bot_std = np.std(bot_data)
    top_std = np.std(top_data)

    if 1.5*bot_std < top_std:
        return 1
    if 1.5*top_std < bot_std:
        return -1

    return 0


def get_forground_mask(image_gray: np.ndarray,
                       bg_thr: float) -> np.ndarray:
    """Get forground mask with only one island where a sphere is located"""
    forground_mask = image_gray > bg_thr

    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    forground_mask = cv2.morphologyEx(
        forground_mask.astype(np.uint8),
        cv2.MORPH_OPEN,
        open_kernel,
        iterations=1
    )

    cnts, _ = cv2.findContours(forground_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(cnts, key=cv2.contourArea)

    forground_mask[:] = 0
    cv2.drawContours(forground_mask, [cnt], -1, 255, thickness=cv2.FILLED)

    return forground_mask.astype(bool)


def smooth_1D_array(arr: np.ndarray,
                    w: int = 11) -> np.ndarray:
    """Smoothing array using convolution (moving average)"""
    return np.convolve(arr.astype(float), np.ones(w)/w, mode='same')


def fit_circle(x: np.ndarray,
               y: np.ndarray) -> tuple[float, float, float]:
    """
        Find the center coordinates and the radius of the circle
    :param x: x coordinate points
    :param y: y coordinate points
    :return: x_c, y_c and radius of the circle
    """
    # build linear system
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x**2 + y**2)

    # solve least squares
    D, E, F = np.linalg.lstsq(A, b, rcond=None)[0]

    # recover cirlce parameters
    x_c = -D / 2
    y_c = -E / 2
    R = np.sqrt(x_c*x_c + y_c*y_c - F)

    return x_c, y_c, R


def find_the_sphere_on_mask(forground_mask: np.ndarray,
                            n_mov_aver: int = 11,
                            sphere_center_to_nozzle_part: float = 0.3,
                            direction: int = 1,
                            min_bg_pixels_on_edges: int = 5,
                            ) -> tuple[float, float, float] | None:
    """
        Function to find the sphere which is at the lowest positon of the forground mask with only one island
    :param forground_mask: forground mask with only one island where sphere is located
    :param n_mov_aver: moving avarage to estimate roughly the center of the sphere
    :param sphere_center_to_nozzle_part: part of the sphere between center and nozzle that should be taken into account
    :param direction: direction for calculations (1 - nozzle on the top, -1 - nozzle on the bottom)
    :param min_bg_pixels_on_edges: minimum number of pixels between the edge of the image and a sphere mask
    :return: x, y and radius of the sphere or None if something is not right
    """
    if direction not in [1, -1]:
        raise ValueError('direction must be either 1 or -1')

    try:
        # count the forground pixels in rows
        y_px_count = np.count_nonzero(forground_mask, axis=1)

        if direction == 1:
            # the lowest possition
            y_e = np.argwhere(y_px_count > 0)[-1][0]
            # smoothing the row counts
            mov_aver = smooth_1D_array(y_px_count[:y_e], w=n_mov_aver)

            # rough estimation of the vertical center position
            y_c_rough = np.argwhere(np.diff(mov_aver) > 0)[-1][0]

            # the highest position
            y_0 = y_c_rough - int((y_e - y_c_rough) * sphere_center_to_nozzle_part)
        else:
            # the highest possition
            y_0 = np.argwhere(y_px_count > 0)[0][0]
            # smoothing the row counts
            mov_aver = smooth_1D_array(y_px_count[y_0:], w=n_mov_aver)

            # rough estimation of the vertical center position
            y_c_rough = np.argwhere(np.diff(mov_aver) < 0)[0][0] + y_0

            # the lowest position
            y_e = y_c_rough + int((y_c_rough - y_0) * sphere_center_to_nozzle_part)

        # checking whether the whole sphere in the field of view
        if (np.any(forground_mask[y_0:y_e+1, :min_bg_pixels_on_edges])
                or np.any(forground_mask[y_0:y_e+1, -min_bg_pixels_on_edges:])
                or y_0 - min_bg_pixels_on_edges < 0 or y_e + min_bg_pixels_on_edges >= len(forground_mask)):
            return None

        sphere_hor_mask = np.sum(forground_mask[y_0:y_e], axis=0)
        sphere_hor_coords = np.argwhere(sphere_hor_mask != 0)
        x_0 = sphere_hor_coords[0, 0]
        x_e = sphere_hor_coords[-1, 0]

        all_coords = np.argwhere(forground_mask[y_0:y_e+1, x_0:x_e+1])
        all_sel_x = np.empty(0)
        all_sel_y = np.empty(0)
        for i in range(y_e - y_0):
            sel_coords = all_coords[all_coords[:, 0] == i]
            all_sel_y = np.append(all_sel_y, (y_0 + i, y_0 + i))
            all_sel_x = np.append(all_sel_x, (sel_coords[0, 1] + x_0, sel_coords[-1, 1] + x_0))

        return fit_circle(all_sel_x, all_sel_y)
    except:
        return None


def get_cut_sphere_mask(x_c_pos: float,
                        y_c_pos: float,
                        radius: float,
                        x_0: int,
                        y_0: int,
                        mask_len: int,
                        top_y: float,
                        bot_y: float) -> np.ndarray:
    """Getting cut at the bottom and at the top sphere mask"""
    x_coords, y_coords = np.meshgrid(np.arange(mask_len), np.arange(mask_len))

    cut_sphere_mask = np.logical_and(
        (x_coords - (x_c_pos - x_0))**2 + (y_coords - (y_c_pos - y_0))**2 < radius**2,
        (y_coords > top_y) & (y_coords < bot_y))

    return cut_sphere_mask


def gaussian_model(x: np.ndarray,
                   a: float,
                   x0: float,
                   sigma: float) -> np.ndarray:
    """Gaussian model without offset"""
    return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))


def gaussian_fit(x: np.ndarray,
                 y: np.ndarray,) -> tuple[float, float, float]:
    """Performing Gaussian fit"""
    x = np.asarray(x)
    y = np.asarray(y)

    x0 = x[np.argmax(y)]
    a0 = np.max(y)
    sigma0 = (np.max(x) - np.min(x)) / 4
    p0 = [a0, x0, sigma0]

    popt, pcov = curve_fit(gaussian_model, x, y, p0=p0)
    a, x0, sigma = popt
    return a, x0, sigma


def get_blur_sigma(image_gray: np.ndarray,
                   x_c_pos: float,
                   y_c_pos: float,
                   radius: float,
                   sphere_center_to_nozzle_part: float = 0.7,
                   direction: int = 1,
                   border_thickness: int = 2) -> float | None:
    """
        Getting the bluring of the border of sphere
    :param image_gray: grayscale image
    :param x_c_pos: x position of center of sphere
    :param y_c_pos: y position of center of sphere
    :param radius: radius of sphere
    :param sphere_center_to_nozzle_part:
    :param direction:
    :param border_thickness:
    :return:
    """
    if sphere_center_to_nozzle_part < 0 or sphere_center_to_nozzle_part > 1:
        raise ValueError('sphere_center_to_nozzle_part must be between 0 and 1')

    if border_thickness < 1:
        raise ValueError('border_thickness must be greater than 0')

    x_0 = int(x_c_pos - radius)
    y_0 = int(y_c_pos - radius)
    mask_len = int(2 * radius + 1)
    sphere_image = image_gray[y_0:y_0 + mask_len, x_0:x_0 + mask_len]

    if direction == 0:
        return np.nan
    elif direction == 1:
        top_y = y_c_pos - y_0 - sphere_center_to_nozzle_part * radius
        bot_y = y_0 + 2 * radius + 1
    elif direction == -1:
        top_y = 0
        bot_y = y_c_pos - y_0 + sphere_center_to_nozzle_part * radius
    else:
        raise ValueError('direction must be either 1, or 0, or -1')

    try:
        border_intensities = []
        for i in range(border_thickness, int(radius/2)):
            # mask of biger sphere
            sphere_mask = get_cut_sphere_mask(x_c_pos, y_c_pos, radius-i+border_thickness, x_0, y_0, mask_len, top_y, bot_y)
            # mask of smaller sphere
            smaller_sphere_mask = get_cut_sphere_mask(x_c_pos, y_c_pos, radius-i, x_0, y_0, mask_len, top_y, bot_y)
            border_intensities.append(np.mean(sphere_image[sphere_mask & ~smaller_sphere_mask]))

        # calculating first derivatives
        dif = np.diff(border_intensities)
        x = np.arange(len(dif))

        # Gaussian fit
        _, _, sigma = gaussian_fit(x, dif)
    except:
        return None

    return np.abs(sigma)
