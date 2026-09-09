"""Functions to work with images"""

__all__ = ["get_sphere_centers_and_blur_sigmas", "adjust_image_center_points"]

import time
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import curve_fit
from ._3dsc_print_debug import DebugInfo


def load_image(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load an image and return gray- and color-scale variants of it"""
    image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    image_color = cv2.cvtColor(image, cv2.COLOR_BAYER_BG2BGR)
    image_gray = cv2.cvtColor(image, cv2.COLOR_BAYER_BG2GRAY)
    return image_gray, image_color


def get_bg_value(image_gray: np.ndarray,
                 bg_height_px: int = 300,
                 perc: float = 99.9,
                 direction: int = 1) -> int:
    """
        Get background intensity from image
    :param image_gray: gray-scale image
    :param bg_height_px: background height in pixels from the bottom of the image
    :param perc: percentile of background intensity
    :param direction: direction for calculations
    :return:
    """
    bg_std = []
    for i in range(2, bg_height_px+1, 1):
        bg_std.append(np.std(image_gray[-i:] if direction == 1 else image_gray[:i]))
    sel_arg = np.argmin(bg_std)+2
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


def debug_images_storing(filename: Path,
                         result: np.ndarray,
                         **kwargs) -> None:
    x_c_pos = kwargs.get('x_c_pos', None)
    y_c_pos = kwargs.get('y_c_pos', None)
    radius = kwargs.get('radius', None)
    print_cur_ret = kwargs.get('print_cur_ret', print)
    if x_c_pos is not None and y_c_pos is not None:
        cv2.circle(result, (round(x_c_pos), round(y_c_pos)), int(radius), (0, 255, 0), 2)
        cv2.circle(result, (round(x_c_pos), round(y_c_pos)), 3, (0, 0, 255), -1)
    cv2.imwrite(filename, result)
    print_cur_ret()


def filtering_data_by_radius(image_filenames: list[Path],
                             sphere_centers: np.ndarray,
                             sigmas: np.ndarray,
                             radii: np.ndarray,
                             debug: bool = False,
                             debug_folder: Path | None = None) -> None:
    """
        Filtering data by radius. If estimated sphere radius is out of statistics the values are replaced with np.nan
    :param image_filenames:
    :param sphere_centers:
    :param sigmas:
    :param radii:
    :param debug:
    :param debug_folder:
    :return:
    """
    # filtering by radius
    std_radii = np.nanstd(radii)
    mean_radius = np.nanmean(radii)
    bad_mask = (np.abs(radii - mean_radius) > 2.5*std_radii) & (~np.isnan(sigmas))
    if debug and debug_folder is not None:
        for each_arg_bad_est in np.arange(len(radii))[bad_mask]:
            _, image_color = load_image(image_filenames[each_arg_bad_est])
            debug_images_storing(
                debug_folder / f"result{each_arg_bad_est:>04d}.png",
                image_color,
                x_c_pos=sphere_centers[each_arg_bad_est, 0],
                y_c_pos=sphere_centers[each_arg_bad_est, 1],
                radius=radii[each_arg_bad_est]
            )
    sigmas[bad_mask] = np.nan
    radii[bad_mask] = np.nan


def get_sphere_centers_and_blur_sigmas(image_filenames: list[Path],
                                       bg_height_px: int = 300,
                                       bg_color_est_perc: float = 99.9,
                                       n_mov_aver: int = 11,
                                       sphere_center_to_nozzle_part: float = 0.3,
                                       min_bg_pixels_on_edges: int = 5,
                                       blur_est_border_thickness: int = 2,
                                       print_debug: DebugInfo = print,
                                       store_debug_images: bool = False,
                                       debug_folder: Path = Path(''),
                                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
        Getting found sphere parameters and bluring sigma at the border of the sphere
    :param image_filenames: list of the paths to images
    :param bg_height_px: estimated background height at the bottom or at the top of each image
    :param bg_color_est_perc: percentile to estimate the background color
    :param n_mov_aver: number of moving average pixels to smooth the intermediate data
    :param sphere_center_to_nozzle_part: part of the sphere between its center and the nozzle that should be taken into account
    :param min_bg_pixels_on_edges: min number of pixels between the edge of the sphere and each edge of the image
    :param blur_est_border_thickness: border thickness of each step along the radius to estimate blurring sigma
    :param print_debug: print debug information if needed
    :param store_debug_images: whether to store the debug images
    :param debug_folder: folder to store debug information
    :return:
    """
    sphere_centers = []
    border_sigmas = []
    radii = []
    image_sizes = []
    all_directions = []

    for i, each_image in enumerate(image_filenames):

        # file to store debug image
        debug_imagefile = debug_folder / f"result{i:>04d}.png"

        sphere_centers.append([np.nan, np.nan])
        border_sigmas.append(np.nan)
        radii.append(np.nan)
        all_directions.append(0)

        starting_time = time.perf_counter()

        # loading the image
        image_gray, image_color = load_image(each_image)
        image_sizes.append(image_gray.shape)

        # getting the direction (1 - nozzle on the top, -1 - nozzle at the bottom, 0 - undefined)
        direction = estimate_direction(image_gray, bg_height_px=bg_height_px//2)
        all_directions[-1] = direction
        print_debug(f"{i:>03d} image - direction: {direction:+}, ", end="")

        # if direction is undefined the measurement should be skipped
        if direction == 0:
            debug_images_storing(debug_imagefile, image_color, print_cur_ret=print_debug)
            continue

        # getting the highest background value (allowing only a few pixels to be higher)
        bg_thr = get_bg_value(image_gray, bg_height_px=bg_height_px, perc=bg_color_est_perc, direction=direction)
        print_debug(f"BG_thr: {bg_thr:0.1f}, ", end="")

        # getting forground mask for the nozzle with a ball only (removing the other islands)
        forground_mask = get_forground_mask(image_gray, bg_thr)

        # searching the sphere on the forground mask
        sphere_params = find_the_sphere_on_mask(
            forground_mask,
            n_mov_aver=n_mov_aver,
            sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
            direction=direction,
            min_bg_pixels_on_edges=min_bg_pixels_on_edges
        )

        # if sphere is not found just continue
        if sphere_params is None:
            debug_images_storing(debug_imagefile, image_color, print_cur_ret=print_debug)
            continue

        x_c_pos, y_c_pos, radius = sphere_params

        # getting the sigmas of edge blurring
        sigma = get_blur_sigma(
            image_gray,
            x_c_pos,
            y_c_pos,
            radius+min_bg_pixels_on_edges,
            sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
            direction=direction,
            border_thickness=blur_est_border_thickness
        )

        # if sigma could not be calculated just continue with another image
        if sigma is None:
            debug_images_storing(debug_imagefile, image_color, x_c_pos=x_c_pos, y_c_pos=y_c_pos, radius=radius,
                                 print_cur_ret=print_debug)
            continue

        print_debug(f"sphere center: ({x_c_pos:>07.2f}, {y_c_pos:>07.2f}), radius: {radius:0.2f}, border sigma: {sigma:>5.2f} "
                    f"time: {time.perf_counter() - starting_time:0.2f} s.")

        # store images if needed
        if store_debug_images:
            debug_images_storing(debug_imagefile, image_color, x_c_pos=x_c_pos, y_c_pos=y_c_pos, radius=radius)

        sphere_centers[-1] = [x_c_pos, y_c_pos]
        border_sigmas[-1] = sigma
        radii[-1] = radius

    sphere_centers = np.array(sphere_centers, dtype=np.float64)
    border_sigmas = np.array(border_sigmas, dtype=np.float64)
    radii = np.array(radii, dtype=np.float64)
    image_sizes = np.array(image_sizes, dtype=np.float64)
    all_directions = np.array(all_directions, dtype=np.int8)

    # filtering the data that has bad radius estimation
    filtering_data_by_radius(
        image_filenames,
        sphere_centers,
        border_sigmas,
        radii,
        debug=debug,
        debug_folder=debug_folder,
    )

    return sphere_centers, border_sigmas, radii, image_sizes, all_directions


def adjust_image_center_points(image_center_points: np.ndarray,
                               radii: np.ndarray,
                               intrinsic_matrix: np.ndarray,
                               ) -> np.ndarray:
    """
        Adjust the center points of spheres using radii and intrinsic matrix. The equation delievered using
        Angle bisector theorem
    :param image_center_points: center points of spheres on the images taken
    :param radii: visual radii of the sphere with bluring
    :param intrinsic_matrix: intrinsic matrix of the camera
    :return: new center points of sphere
    """
    # camera principal point
    c_xy = np.array([intrinsic_matrix[0, 2], intrinsic_matrix[1, 2]])[None, :]

    # points with added radii
    xy_plus = image_center_points + radii[:, None]
    # points with subtracted radii
    xy_minus = image_center_points - radii[:, None]

    # focal distances
    f_xy = np.array([intrinsic_matrix[0, 0], intrinsic_matrix[1, 1]])[None, :]

    # distance ratio used in angle bisector theorem
    dist_ratio = np.sqrt(((c_xy - xy_plus) ** 2 + f_xy ** 2) / ((c_xy - xy_minus) ** 2 + f_xy ** 2))

    # calculation of new center points
    new_image_center_points = image_center_points + radii[:, None] * (1 - dist_ratio) / (1 + dist_ratio)

    return new_image_center_points
