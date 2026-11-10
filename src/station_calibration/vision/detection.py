# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Low-level sphere detection and edge-blur estimation."""

__all__ = [
    "get_bg_value",
    "get_bg_noise_threshold",
    "estimate_direction",
    "get_forground_mask",
    "smooth_1D_array",
    "fit_circle",
    "fit_circle_with_covariance",
    "find_the_sphere_on_mask",
    "get_cut_sphere_mask",
    "gaussian_model",
    "gaussian_fit",
    "get_blur_sigma",
]

import cv2
import numpy as np
from scipy.optimize import curve_fit

# A sub-pixel circle fit is only accepted when enough rays resolve the edge and
# the fitted points survive the MAD trim.  The binary mask remains the fallback
# for strongly defocused or low-contrast frames where the 50 % crossing is not
# well defined.  The search window is blur-aware from the first attempt; a
# fixed 20 % window can truncate the inner plateau on defocused edges.
_MIN_SUBPIXEL_POINTS = 16
_MIN_TRIMMED_SUBPIXEL_POINTS = 12
_MAX_SUBPIXEL_SEARCH_FRACTION = 0.5
_SUBPIXEL_SEARCH_SIGMA_FACTOR = 3.0
_SUBPIXEL_SEARCH_GROWTH = 1.5

# Scale factor that turns the median absolute deviation into a Gaussian-
# equivalent standard deviation for normally distributed noise.
_MAD_TO_SIGMA = 1.4826


def _background_prefix(image_gray: np.ndarray,
                       bg_height_px: int = 300,
                       direction: int = 1,
                       start_from: int = 10) -> np.ndarray:
    """
        Return the quietest prefix of the background band.

        Rows are ordered from the background side inwards, so the prefix stops
        before a sphere or nozzle enters the band and its statistics stay
        representative of the empty background.
    """
    image_gray = np.asarray(image_gray)
    if image_gray.ndim != 2 or 0 in image_gray.shape:
        raise ValueError("image_gray must be a non-empty 2D array")
    if direction == 1:
        band = image_gray[::-1, :]
    elif direction == -1:
        band = image_gray
    else:
        raise ValueError("direction must be either 1 or -1")
    if start_from < 1:
        raise ValueError("start_from must be positive")
    if bg_height_px < start_from:
        raise ValueError("bg_height_px must be at least start_from")

    n_rows, width = band.shape
    max_rows = min(int(bg_height_px), n_rows)
    if max_rows <= 0:
        raise ValueError("image_gray must contain at least one row")

    band = band[:max_rows]
    row_sums = band.sum(axis=1, dtype=np.float64)
    row_sum_squares = np.einsum(
        "ij,ij->i", band, band, dtype=np.float64, optimize=True
    )
    prefix_sums = np.cumsum(row_sums, dtype=np.float64)
    prefix_sum_squares = np.cumsum(row_sum_squares, dtype=np.float64)
    counts = np.arange(1, max_rows + 1, dtype=np.float64) * width
    means = prefix_sums / counts
    variances = prefix_sum_squares / counts - means * means
    prefix_stds = np.sqrt(np.maximum(variances, 0.0))

    if max_rows < start_from:
        sel_arg = int(start_from)
    else:
        if int(bg_height_px) <= max_rows:
            candidate_stds = prefix_stds[start_from - 1:int(bg_height_px)]
        else:
            candidate_stds = np.concatenate(
                (
                    prefix_stds[start_from - 1:max_rows],
                    np.full(
                        int(bg_height_px) - max_rows,
                        prefix_stds[-1],
                        dtype=np.float64,
                    ),
                )
            )
        sel_arg = int(np.argmin(candidate_stds) + start_from)

    values = band[: min(sel_arg, max_rows)]
    return values.reshape(-1)


def get_bg_value(image_gray: np.ndarray,
                 bg_height_px: int = 300,
                 perc: float = 99.9,
                 direction: int = 1,
                 start_from: int = 10) -> float:
    """
        Get background intensity from image
    :param image_gray: gray-scale image
    :param bg_height_px: background height in pixels from the bottom of the image
    :param perc: percentile of background intensity
    :param direction: direction for calculations
    :param start_from: starting arg for estimation
    :return: percentile of the quietest background prefix
    """
    try:
        perc = float(perc)
    except (TypeError, ValueError):
        raise ValueError("perc must be in (0, 100]") from None
    if not 0.0 < perc <= 100.0:
        raise ValueError("perc must be in (0, 100]")

    values = _background_prefix(
        image_gray,
        bg_height_px=bg_height_px,
        direction=direction,
        start_from=start_from,
    )
    return float(np.percentile(values, perc))


def get_bg_noise_threshold(image_gray: np.ndarray,
                           bg_height_px: int = 300,
                           direction: int = 1,
                           start_from: int = 10,
                           n_sigma: float = 5.0,
                           percentile_floor: float | None = None) -> float:
    """
        Estimate a background threshold from the robust background noise.

        The threshold is ``median + n_sigma * 1.4826 * MAD`` over the quietest
        prefix of the background band.  Unlike a high percentile, ``n_sigma``
        is an explicit confidence level and does not depend on the number of
        pixels in the band.

        On quantized 8-bit backgrounds more than half of the prefix pixels may
        equal the median.  ``MAD`` is then zero and the threshold collapses to
        the median, which can turn the sensor pattern into foreground.  Pass
        ``percentile_floor`` (for example 99.999) to keep the result at or
        above the legacy percentile of the same prefix.

    :param image_gray: gray-scale image
    :param bg_height_px: background height in pixels from the bottom or top
    :param direction: 1 for a noisy top (nozzle above), -1 for a noisy bottom
    :param start_from: minimum number of background rows to use
    :param n_sigma: number of robust standard deviations above the median
    :param percentile_floor: optional percentile of the prefix used as a lower bound
    :return: background threshold
    """
    try:
        n_sigma = float(n_sigma)
    except (TypeError, ValueError):
        raise ValueError("n_sigma must be positive and finite") from None
    if not np.isfinite(n_sigma) or n_sigma <= 0.0:
        raise ValueError("n_sigma must be positive and finite")

    floor: float | None = None
    if percentile_floor is not None:
        try:
            floor = float(percentile_floor)
        except (TypeError, ValueError):
            raise ValueError("percentile_floor must be in (0, 100]") from None
        if not 0.0 < floor <= 100.0:
            raise ValueError("percentile_floor must be in (0, 100]")

    values = _background_prefix(
        image_gray,
        bg_height_px=bg_height_px,
        direction=direction,
        start_from=start_from,
    )
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    threshold = median + n_sigma * _MAD_TO_SIGMA * mad
    if floor is not None:
        threshold = max(threshold, float(np.percentile(values, floor)))
    return threshold


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
    image_gray = np.asarray(image_gray)
    if image_gray.ndim != 2 or 0 in image_gray.shape:
        raise ValueError("image_gray must be a non-empty 2D array")
    if bg_height_px < 1:
        raise ValueError("bg_height_px must be positive")

    # Keep the two bands disjoint.  On a frame shorter than twice the requested
    # band, slicing the whole image for both sides would compare the same
    # pixels and make a real direction look undefined.
    band_height = min(int(bg_height_px), int(image_gray.shape[0]) // 2)
    if band_height < 1:
        return 0

    bot_data = image_gray[-band_height:]
    top_data = image_gray[:band_height]
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
    image_gray = np.asarray(image_gray)
    if image_gray.ndim != 2 or 0 in image_gray.shape:
        raise ValueError("image_gray must be a non-empty 2D array")
    try:
        bg_thr = float(bg_thr)
    except (TypeError, ValueError):
        raise ValueError("bg_thr must be a finite scalar") from None
    if not np.isfinite(bg_thr):
        raise ValueError("bg_thr must be finite")

    forground_mask = image_gray > bg_thr

    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    forground_mask_u8 = cv2.morphologyEx(
        forground_mask.astype(np.uint8),
        cv2.MORPH_OPEN,
        open_kernel,
        iterations=1
    )

    cnts, _ = cv2.findContours(forground_mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return np.zeros_like(image_gray, dtype=bool)

    cnt = max(cnts, key=cv2.contourArea)

    forground_mask_u8[:] = 0
    cv2.drawContours(forground_mask_u8, [cnt], -1, 255, thickness=cv2.FILLED)

    return forground_mask_u8.astype(bool)


def smooth_1D_array(arr: np.ndarray,
                    w: int = 11) -> np.ndarray:
    """Smoothing array using convolution (moving average)"""
    return np.convolve(arr.astype(float), np.ones(w)/w, mode='same')


def fit_circle_with_covariance(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[float, float, float, np.ndarray]:
    """
        Fit a circle and estimate the 2x2 covariance of its centre.

        The algebraic Kasa fit is linear in the parameters ``D, E, F``.  Its
        parameter covariance is ``sigma^2 (A^T A)^-1`` with ``sigma^2`` taken
        from the algebraic residuals.  Since ``x_c = -D/2`` and ``y_c = -E/2``,
        the centre covariance is one quarter of the leading 2x2 block.

    :param x: x coordinate points
    :param y: y coordinate points
    :return: x_c, y_c, radius, and the 2x2 centre covariance
    """
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    if x.size != y.size:
        raise ValueError("x and y must have the same length")
    if x.size < 3:
        raise ValueError("at least three points are required to fit a circle")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("circle points must be finite")

    # Centre the coordinates before building the linear system.  This keeps the
    # normal equations well conditioned even though raw pixel coordinates are
    # O(1000) and their squares are O(1e6).
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    x_centered = x - x_mean
    y_centered = y - y_mean

    # build linear system
    A = np.column_stack([x_centered, y_centered, np.ones_like(x)])
    b = -(x_centered**2 + y_centered**2)

    # solve least squares
    D, E, F = np.linalg.lstsq(A, b, rcond=None)[0]

    # recover circle parameters
    x_c_centered = -D / 2
    y_c_centered = -E / 2
    x_c = x_mean + x_c_centered
    y_c = y_mean + y_c_centered
    R = np.sqrt(x_c_centered*x_c_centered + y_c_centered*y_c_centered - F)

    residual = A @ np.array([D, E, F], dtype=np.float64) - b
    degrees_of_freedom = max(int(x.size) - 3, 1)
    variance = float(np.dot(residual, residual) / degrees_of_freedom)
    if not np.isfinite(variance) or variance < 0.0:
        variance = 0.0

    # cov(p) = variance * A^+ (A^+)^T, which is more stable than explicitly
    # forming the normal-matrix inverse.
    A_pinv = np.linalg.pinv(A)
    center_covariance = 0.25 * variance * (A_pinv[:2, :] @ A_pinv[:2, :].T)
    center_covariance = 0.5 * (center_covariance + center_covariance.T)

    return x_c, y_c, R, center_covariance


def fit_circle(x: np.ndarray,
               y: np.ndarray) -> tuple[float, float, float]:
    """
        Find the center coordinates and the radius of the circle
    :param x: x coordinate points
    :param y: y coordinate points
    :return: x_c, y_c and radius of the circle
    """
    x_c, y_c, R, _ = fit_circle_with_covariance(x, y)
    return x_c, y_c, R


def _first_upward_crossing(profile: np.ndarray,
                           level: float) -> float | None:
    """
        Locate the first upward crossing of ``level`` along a 1D profile.

        The profile must be ordered from the outside of the object towards its
        interior.  The returned value is a fractional index: ``k - 1 + t``
        means that the crossing lies between samples ``k - 1`` and ``k``.
    """
    if profile.size < 2:
        return None
    above = profile >= level
    # The crossing must be inside the window, so the first sample has to be
    # below the level and a later one has to reach it.
    if above[0] or not np.any(above):
        return None
    k = int(np.argmax(above))
    low = float(profile[k - 1])
    high = float(profile[k])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return None
    fraction = (level - low) / (high - low)
    return float(k - 1 + np.clip(fraction, 0.0, 1.0))


def _sample_radial_profiles(image_gray: np.ndarray,
                            x_c: float,
                            y_c: float,
                            angles: np.ndarray,
                            radii: np.ndarray,
                            ) -> np.ndarray:
    """Sample image intensity along radial profiles (angles x radii)."""
    cos_a = np.cos(angles)[:, None]
    sin_a = np.sin(angles)[:, None]
    map_x = (x_c + radii[None, :] * cos_a).astype(np.float32)
    map_y = (y_c + radii[None, :] * sin_a).astype(np.float32)
    return cv2.remap(
        np.asarray(image_gray, dtype=np.float32),
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _subpixel_radial_points(image_gray: np.ndarray,
                            x_c: float,
                            y_c: float,
                            radius: float,
                            direction: int,
                            sphere_center_to_nozzle_part: float,
                            search_px: int | None = None,
                            n_rays: int = 360,
                            ) -> tuple[np.ndarray, np.ndarray]:
    """
        Locate sphere boundary points at the 50 % radial intensity crossing.

        Rays are sampled from the rough circle outwards to inwards, so every
        profile crosses the edge normally. This avoids the noisy, nearly
        horizontal rows at the top and bottom of a row-wise scan. The local
        background and object intensity are estimated on each ray, which also
        handles a smooth illumination gradient across the sphere.
    """
    search = max(4, int(0.2 * radius)) if search_px is None else int(search_px)
    n_samples = 2 * search + 1
    radii = np.linspace(radius + search, radius - search, n_samples)

    angles = np.linspace(0.0, 2.0 * np.pi, n_rays, endpoint=False)
    sin_a = np.sin(angles)
    if direction == 1:
        angles = angles[sin_a >= -sphere_center_to_nozzle_part]
    else:
        angles = angles[sin_a <= sphere_center_to_nozzle_part]
    if angles.size == 0:
        return np.empty(0), np.empty(0)

    height, width = image_gray.shape
    cos_a = np.cos(angles)[:, None]
    sin_a = np.sin(angles)[:, None]
    sample_x = x_c + radii[None, :] * cos_a
    sample_y = y_c + radii[None, :] * sin_a
    inside = (
        (sample_x >= 0.0)
        & (sample_x <= width - 1.0)
        & (sample_y >= 0.0)
        & (sample_y <= height - 1.0)
    ).all(axis=1)
    angles = angles[inside]
    if angles.size == 0:
        return np.empty(0), np.empty(0)

    profiles = _sample_radial_profiles(image_gray, x_c, y_c, angles, radii)
    # Use only the outer/inner eighth for the plateau levels.  A quarter is too
    # wide when the edge transition nearly fills the search window, which is
    # common for strongly defocused small spheres.
    inner = max(3, n_samples // 8)
    last_valid = n_samples - inner - 1

    xs: list[float] = []
    ys: list[float] = []
    for angle, profile in zip(angles, profiles):
        background = float(np.median(profile[:inner]))
        foreground = float(np.median(profile[-inner:]))
        if (
            not np.isfinite(background)
            or not np.isfinite(foreground)
            or foreground <= background
        ):
            continue
        # The outer and inner plateaus must be flat.  With a too-small search
        # window the 20/80 levels are computed from a still-rising inner edge,
        # which makes the transition look narrower than it is.
        profile_range = float(
            np.percentile(profile, 95) - np.percentile(profile, 5)
        )
        step = max(1, inner // 2)
        outer_rise = float(
            np.median(profile[step:inner]) - np.median(profile[:step])
        )
        inner_rise = float(
            np.median(profile[-step:]) - np.median(profile[-inner:-step])
        )
        if profile_range > 0 and (outer_rise + inner_rise) > 0.1 * profile_range:
            continue
        span = foreground - background
        fraction_20 = _first_upward_crossing(profile, background + 0.2 * span)
        fraction = _first_upward_crossing(profile, background + 0.5 * span)
        fraction_80 = _first_upward_crossing(profile, background + 0.8 * span)
        if fraction_20 is None or fraction is None or fraction_80 is None:
            continue
        # The 20 % and 80 % crossings must be fully inside the profile, and the
        # edge transition must leave enough plateau on both sides.  Otherwise
        # the search window does not contain the edge transition and the
        # crossing is not trustworthy.
        transition_width = fraction_80 - fraction_20
        if not (
            1.0 <= fraction_20 < fraction < fraction_80 <= n_samples - 2.0
            and transition_width <= (n_samples - 1) - 2 * inner
            and inner <= fraction <= last_valid
        ):
            continue
        r = float(np.interp(fraction, np.arange(n_samples), radii))
        xs.append(x_c + r * np.cos(angle))
        ys.append(y_c + r * np.sin(angle))

    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def find_the_sphere_on_mask(forground_mask: np.ndarray,
                            n_mov_aver: int = 11,
                            sphere_center_to_nozzle_part: float = 0.3,
                            direction: int = 1,
                            min_bg_pixels_on_edges: int = 5,
                            return_covariance: bool = False,
                            image_gray: np.ndarray | None = None,
                            edge_search_px: int | None = None,
                            ) -> tuple[float, float, float] | tuple[float, float, float, np.ndarray] | None:
    """
        Function to find the sphere which is at the lowest positon of the forground mask with only one island
    :param forground_mask: forground mask with only one island where sphere is located
    :param n_mov_aver: moving avarage to estimate roughly the center of the sphere
    :param sphere_center_to_nozzle_part: part of the sphere between center and nozzle that should be taken into account
    :param direction: direction for calculations (1 - nozzle on the top, -1 - nozzle on the bottom)
    :param min_bg_pixels_on_edges: minimum number of pixels between the edge of the image and a sphere mask
    :param return_covariance: whether to append the fitted centre covariance to the result
    :param image_gray: optional gray-scale image; when given, radial edges are refined to the sub-pixel 50 % intensity crossing
    :param edge_search_px: optional search window for the sub-pixel crossing in pixels
    :return: x, y and radius of the sphere or None if something is not right
    """
    if direction not in [1, -1]:
        raise ValueError('direction must be either 1 or -1')
    if image_gray is not None:
        image_gray = np.asarray(image_gray)
        if image_gray.shape != forground_mask.shape:
            raise ValueError(
                "image_gray and forground_mask must have the same shape"
            )
    if edge_search_px is not None and int(edge_search_px) < 1:
        raise ValueError("edge_search_px must be positive")
    if not np.any(forground_mask):
        return None

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

        band_rows = y_e - y_0
        if band_rows <= 0:
            return None

        all_coords = np.argwhere(forground_mask[y_0:y_e+1, x_0:x_e+1])
        if all_coords.size == 0:
            return None

        # The original loop processes rows 0..band_rows-1 and ignores the last
        # row of the slice, so keep that behavior.
        row_ids = all_coords[:, 0]
        col_ids = all_coords[:, 1]
        valid = row_ids < band_rows
        if not np.any(valid):
            return None
        row_ids = row_ids[valid]
        col_ids = col_ids[valid]

        row_counts = np.bincount(row_ids, minlength=band_rows)
        if np.any(row_counts == 0):
            return None

        left = np.full(band_rows, np.iinfo(col_ids.dtype).max, dtype=col_ids.dtype)
        right = np.full(band_rows, np.iinfo(col_ids.dtype).min, dtype=col_ids.dtype)
        np.minimum.at(left, row_ids, col_ids)
        np.maximum.at(right, row_ids, col_ids)

        row_offset = np.arange(band_rows, dtype=np.float64)
        left_f = left.astype(np.float64)
        right_f = right.astype(np.float64)

        all_sel_x = np.empty(2 * band_rows, dtype=np.float64)
        all_sel_y = np.empty(2 * band_rows, dtype=np.float64)
        all_sel_x[0::2] = left_f + x_0
        all_sel_x[1::2] = right_f + x_0
        all_sel_y[0::2] = y_0 + row_offset
        all_sel_y[1::2] = y_0 + row_offset

        if image_gray is not None:
            x_c_int, y_c_int, radius_int = fit_circle(all_sel_x, all_sel_y)
            default_search = max(4, int(0.2 * radius_int))
            max_search = max(
                default_search,
                int(_MAX_SUBPIXEL_SEARCH_FRACTION * radius_int),
            )

            if edge_search_px is not None:
                search = int(edge_search_px)
            else:
                # A 20 % window can be narrower than the blurred edge
                # transition.  That truncates the inner plateau and biases the
                # 50 % crossing outward.  Use a blur-aware window from the
                # start instead of waiting until the default window collects
                # too few points.
                sigma_guess = get_blur_sigma(
                    image_gray,
                    x_c_int,
                    y_c_int,
                    radius_int,
                    sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
                    direction=direction,
                )
                search = default_search
                if (
                    sigma_guess is not None
                    and np.isfinite(sigma_guess)
                    and sigma_guess > 0
                ):
                    search = max(
                        search,
                        int(np.ceil(_SUBPIXEL_SEARCH_SIGMA_FACTOR * sigma_guess)),
                    )
                else:
                    search = max(search, 2 * default_search)
                # Keep a visible expansion even for small sigma; at very low
                # blur the 20 % window is still unnecessarily tight.
                search = max(
                    search,
                    int(np.ceil(_SUBPIXEL_SEARCH_GROWTH * default_search)),
                )
                search = min(search, max_search)

            sub_x, sub_y = _subpixel_radial_points(
                image_gray,
                x_c_int,
                y_c_int,
                radius_int,
                direction,
                sphere_center_to_nozzle_part,
                search_px=search,
            )

            # If the blur-aware window still does not resolve enough rays,
            # retry once with the largest allowed window.  An explicit search
            # override is always honoured without an automatic retry.
            if (
                sub_x.size < _MIN_SUBPIXEL_POINTS
                and edge_search_px is None
                and search < max_search
            ):
                sub_x, sub_y = _subpixel_radial_points(
                    image_gray,
                    x_c_int,
                    y_c_int,
                    radius_int,
                    direction,
                    sphere_center_to_nozzle_part,
                    search_px=max_search,
                )

            if sub_x.size >= _MIN_SUBPIXEL_POINTS:
                try:
                    x_c, y_c, radius = fit_circle(sub_x, sub_y)
                except (ValueError, np.linalg.LinAlgError):
                    pass
                else:
                    if np.isfinite(radius) and radius > 0:
                        residual = np.hypot(sub_x - x_c, sub_y - y_c) - radius
                        median = float(np.median(residual))
                        mad = 1.4826 * float(np.median(np.abs(residual - median)))
                        if np.isfinite(mad) and mad > 0:
                            keep = np.abs(residual - median) <= 3.0 * mad
                        else:
                            keep = np.ones(sub_x.size, dtype=bool)
                        if (
                            np.count_nonzero(keep)
                            >= _MIN_TRIMMED_SUBPIXEL_POINTS
                        ):
                            all_sel_x = sub_x[keep]
                            all_sel_y = sub_y[keep]

        if return_covariance:
            return fit_circle_with_covariance(all_sel_x, all_sel_y)
        return fit_circle(all_sel_x, all_sel_y)
    except Exception:  # noqa: BLE001 - degenerate masks mean no detection
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

    popt, _pcov = curve_fit(gaussian_model, x, y, p0=p0)
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
    except Exception:  # noqa: BLE001 - a failed fit means no usable sigma
        return None

    return np.abs(sigma)
