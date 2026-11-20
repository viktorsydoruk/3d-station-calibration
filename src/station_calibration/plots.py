# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Functions to visualize results."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np


def _pyplot():
    """Import pyplot only when a plot is actually requested."""
    import matplotlib.pyplot as plt

    return plt


def apply_own_style_to_mpl(font_size: float = 8) -> None:
    """Apply the shared Matplotlib style used by calibration plots."""
    import matplotlib as mpl

    mpl.rcParams['font.size'] = font_size
    mpl.rcParams['text.color'] = '#68686C'
    mpl.rcParams['legend.fontsize'] = font_size
    mpl.rcParams['figure.titlesize'] = font_size
    mpl.rcParams['axes.titlecolor'] = '#68686C'
    mpl.rcParams['axes.labelcolor'] = '#68686C'
    mpl.rcParams['axes.titlesize'] = font_size
    mpl.rcParams['axes.labelsize'] = font_size
    mpl.rcParams['xtick.labelcolor'] = '#C7C7CF'
    mpl.rcParams['ytick.labelcolor'] = '#C7C7CF'
    mpl.rcParams['xtick.labelsize'] = font_size
    mpl.rcParams['ytick.labelsize'] = font_size


def visualize_image_center_points(center_points: np.ndarray,
                                  sigmas: np.ndarray,
                                  image_size_xy: tuple[int, int],
                                  camera_principal_point: np.ndarray,
                                  nozzle_home_pos: np.ndarray | None,
                                  closest_image_arg: int | None,
                                  n_distortion_coefs: int,
                                  debug_folder: Path) -> None:
    apply_own_style_to_mpl()
    plt = _pyplot()

    plt.scatter(center_points[:, 0], center_points[:, 1], c=sigmas)
    plt.colorbar()

    # showing camera principal_point
    plt.axvline(camera_principal_point[0], c='tab:red', linestyle='--', alpha=0.5)
    plt.axhline(camera_principal_point[1], c='tab:red', linestyle='--', alpha=0.5)

    if nozzle_home_pos is not None:
        plt.scatter(*nozzle_home_pos, c='tab:red')

    if closest_image_arg is not None:
        plt.scatter(*center_points[closest_image_arg], c='tab:red', s=10)

    plt.gca().xaxis.set_ticks_position('both')
    plt.gca().yaxis.set_ticks_position('both')
    plt.gca().xaxis.set_tick_params(labeltop=True, labelbottom=True)
    plt.gca().yaxis.set_tick_params(labeltop=True, labelbottom=True)
    plt.ylim(image_size_xy[1], 0)
    plt.xlim(0, image_size_xy[0])
    plt.tight_layout()
    plt.savefig(debug_folder / f'center_points_{n_distortion_coefs:>02d}.png')
    plt.close()


def visualize_radii(robot_positions: np.ndarray,
                    extrinsic_matrix: np.ndarray,
                    radii: np.ndarray,
                    sigmas: np.ndarray,
                    debug_folder: Path) -> None:

    coords = np.dot(extrinsic_matrix[None, :3, :3], robot_positions[:, :, None])[0, 2, :, 0]

    apply_own_style_to_mpl()
    plt = _pyplot()

    plt.plot(coords, radii, '.', label="R")
    plt.plot(coords, radii-sigmas, '.', label=r"R-$\sigma$")
    plt.plot(coords, radii-1.5*sigmas, '.', label=r"R-1.5$\bullet \sigma$")
    plt.plot(coords, radii-2*sigmas, '.', label=r"R-2$\bullet \sigma$")

    plt.xlabel("z-depth (mm)")
    plt.ylabel("sphere radius, R (px)")

    plt.legend()
    plt.tight_layout()
    plt.savefig(debug_folder / 'radii_in_depth.png')
    plt.close()


def visualize_sigmas(robot_positions: np.ndarray,
                     extrinsic_matrix: np.ndarray,
                     sigmas: np.ndarray,
                     debug_folder: Path) -> None:

    coords = np.dot(extrinsic_matrix[None, :3, :3], robot_positions[:, :, None])[0, 2, :, 0]

    apply_own_style_to_mpl()
    plt = _pyplot()

    plt.plot(coords, sigmas, '.')

    plt.xlabel("z-depth (mm)")
    plt.ylabel("bluring sigma (px)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'sigmas_in_depth.png')
    plt.close()


def visualize_nozzle_and_home_pos_estimation(all_plots_params: dict,
                                             debug_folder: Path) -> None:
    visualize_scale_coef_estimation(debug_folder=debug_folder, **all_plots_params['scaling_visualization'])
    visualize_n_sigma_estimation(debug_folder=debug_folder, **all_plots_params['n_sigma_estimation'])
    visualize_sphere_radius_estimation(debug_folder=debug_folder, **all_plots_params['sphere_radius_estimation'])
    visualize_sphere_radius_vs_depth(debug_folder=debug_folder, **all_plots_params['sphere_radius_vs_depth'])



def visualize_scale_coef_estimation(z_pos: np.ndarray,
                                    scale: np.ndarray,
                                    fit_popt: np.ndarray,
                                    debug_folder: Path) -> None:
    apply_own_style_to_mpl()
    plt = _pyplot()

    plt.scatter(z_pos, scale)
    x = np.linspace(np.min(z_pos), np.max(z_pos), 101)
    y = np.polyval(fit_popt, x)
    plt.plot(x, y, 'tab:red')
    plt.xlabel("rel. z-depth (mm)")
    plt.ylabel("scale (mm/px)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'scale_coef_estimation.png')
    plt.close()


def visualize_n_sigma_estimation(n_sigmas: np.ndarray,
                                 std_radii: np.ndarray,
                                 debug_folder: Path,
                                 confidence: dict[str, Any] | None = None) -> None:

    apply_own_style_to_mpl()
    plt = _pyplot()

    plt.plot(n_sigmas, std_radii)
    if confidence is not None:
        ci_low = confidence.get("ci_low")
        ci_high = confidence.get("ci_high")
        if ci_low is not None and ci_high is not None:
            plt.axvspan(
                float(ci_low),
                float(ci_high),
                color="tab:orange",
                alpha=0.2,
                label="95% bootstrap CI",
            )
            plt.legend()

    plt.xlabel("n_sigma (px)")
    plt.ylabel("std_radii (px)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'n_sigma_estimation.png')
    plt.close()


def visualize_sphere_radius_estimation(z_pos: np.ndarray,
                                       radii: np.ndarray,
                                       sigmas: np.ndarray,
                                       coef_for_radii: np.ndarray,
                                       n_sigma_est: float,
                                       debug_folder: Path) -> None:
    apply_own_style_to_mpl()
    plt = _pyplot()

    plt.scatter(z_pos, 2*radii*coef_for_radii, label="diam")
    plt.scatter(z_pos, 2*(radii-n_sigma_est*sigmas)*coef_for_radii, label=rf"diam-{2*n_sigma_est:0.2f}$\sigma$")
    plt.scatter(z_pos, 2*(radii-2*sigmas)*coef_for_radii, label=r"diam-4$\sigma$")
    plt.legend()

    sphere_radius = np.mean((radii-n_sigma_est*sigmas)*coef_for_radii)
    plt.axhline(sphere_radius*2)

    plt.xlabel("rel. z-depth (mm)")
    plt.ylabel("sphere diameter (mm)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'sphere_diam_estimation.png')
    plt.close()


def visualize_sphere_radius_vs_depth(z_pos: np.ndarray,
                                     radii: np.ndarray,
                                     sigmas: np.ndarray,
                                     coef_for_radii: np.ndarray,
                                     n_sigma_est: float,
                                     debug_folder: Path) -> None:
    apply_own_style_to_mpl()
    plt = _pyplot()

    est_radii = 2*(radii-n_sigma_est*sigmas)*coef_for_radii
    popt = np.polyfit(z_pos, est_radii, deg=2)
    plt.scatter(z_pos, est_radii)
    z_plot_pos = np.linspace(np.min(z_pos), np.max(z_pos), 101)
    plt.plot(z_plot_pos, np.polyval(popt, z_plot_pos), 'tab:red')

    plt.xlabel("rel. z-depth (mm)")
    plt.ylabel("sphere diameter (mm)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'sphere_diam_vs_depth.png')
    plt.close()

    diam = np.polyval(popt, 0)
    plt.scatter(z_pos, (est_radii-diam)/diam*100)


    plt.xlabel("rel. z-depth (mm)")
    plt.ylabel("sphere diameter rel. error (%)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'sphere_diam_rel_error_vs_depth.png')
    plt.close()

def visualize_residuals(residuals: np.ndarray,
                        center_points_adjusted: np.ndarray,
                        debug_folder: Path,
                        image_size_xy: tuple[int, int]) -> None:
    apply_own_style_to_mpl()
    plt = _pyplot()

    residuals_xy = residuals.reshape(-1, 2)
    distance = np.sqrt(np.sum(residuals_xy**2, axis=1))
    plt.quiver(
        *center_points_adjusted.T,
        *residuals_xy.T, distance,
        angles="xy", scale_units="xy", scale=0.2,
        cmap='Reds', pivot="middle", width=0.005
    )
    plt.xlabel("Image X (px)")
    plt.ylabel("Image Y (px)")

    plt.xlim(0, image_size_xy[0])
    plt.ylim(image_size_xy[1], 0)

    cbar = plt.colorbar()
    cbar.set_label("Residuals distance (px)")
    plt.tight_layout()
    plt.savefig(debug_folder / f'2D redidual vectors - {len(center_points_adjusted)} points.png')
    plt.close()


def visualize_debug_data(data: list[list[str | float | np.floating | np.integer]],
                         debug_folder: Path) -> None:
    apply_own_style_to_mpl()
    plt = _pyplot()

    names = data[0]
    values = np.array(data[1:], dtype=float).T

    plt.errorbar(values[0], values[2], yerr=values[3], label=names[2])
    plt.errorbar(values[0], values[4], yerr=values[5], label=names[4])
    plt.xlabel(f"{names[0]}")
    plt.ylabel("Focal length (px)")

    plt.legend()
    plt.tight_layout()
    plt.savefig(debug_folder / 'focal length vs number of points.png')
    plt.close()

    plt.errorbar(values[1], values[2], yerr=values[3], label=names[2])
    plt.errorbar(values[1], values[4], yerr=values[5], label=names[4])
    plt.xlabel(f"{names[1]}")
    plt.ylabel("Focal length (px)")

    plt.legend()
    plt.tight_layout()
    plt.savefig(debug_folder / 'focal length vs left number of points.png')
    plt.close()

    plt.errorbar(values[0], values[6], yerr=values[7], label=names[6])
    plt.xlabel(f"{names[0]}")
    plt.ylabel(f"{names[6]} (mm)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'camera distance vs number of points.png')
    plt.close()

    plt.errorbar(values[1], values[6], yerr=values[7], label=names[6])
    plt.xlabel(f"{names[1]}")
    plt.ylabel(f"{names[6]} (mm)")

    plt.tight_layout()
    plt.savefig(debug_folder / 'camera distance vs left number of points.png')
    plt.close()


    plt.plot(values[0], values[-1], label=names[0])
    plt.plot(values[1], values[-1], label=names[1])
    plt.xlabel(f"{names[0]}")
    plt.ylabel(f"{names[-1]}")

    plt.legend()
    plt.tight_layout()
    plt.savefig(debug_folder / 'RMSE vs number of points.png')
    plt.close()


def visualize_sphere_analysis(image_gray: np.ndarray,
                              image_color: np.ndarray | None,
                              *,
                              observation: Any,
                              direction: int,
                              bg_threshold: float,
                              debug_folder: Path,
                              sphere_center_to_nozzle_part: float = 0.3,
                              n_mov_aver: int = 11,
                              min_bg_pixels_on_edges: int = 5,
                              filename: str = "sphere_analysis",
                              dpi: int = 300) -> Path | None:
    """Render a four-panel diagnostic for one real sphere frame.

    The panels show the raw frame, the foreground mask, the binary and sub-pixel
    circle fits, and a radial intensity profile through the detected edge.  The
    function is called from the folder workflow when debug output is enabled;
    it also produces the publication figure in ``paper/figures``.
    """
    if observation is None:
        return None

    from matplotlib.patches import Circle

    from .vision.detection import (
        _first_upward_crossing,
        _sample_radial_profiles,
        _subpixel_radial_points,
        _subpixel_search_window,
        find_the_sphere_on_mask,
        get_forground_mask,
    )

    image_gray = np.asarray(image_gray)
    if image_gray.ndim != 2 or image_gray.size == 0:
        raise ValueError("image_gray must be a non-empty 2D array")

    mask = get_forground_mask(image_gray, float(bg_threshold))
    binary = find_the_sphere_on_mask(
        mask,
        n_mov_aver=n_mov_aver,
        sphere_center_to_nozzle_part=sphere_center_to_nozzle_part,
        direction=direction,
        min_bg_pixels_on_edges=min_bg_pixels_on_edges,
        image_gray=None,
    )
    if binary is None:
        return None
    x_bin, y_bin, radius_bin = (float(value) for value in binary)

    x_sub = float(observation.x)
    y_sub = float(observation.y)
    radius_sub = float(observation.radius)
    sigma = float(observation.sigma)
    search, _ = _subpixel_search_window(radius_bin, sigma)
    sub_x, sub_y = _subpixel_radial_points(
        image_gray,
        x_bin,
        y_bin,
        radius_bin,
        direction,
        sphere_center_to_nozzle_part,
        search_px=search,
    )

    # One radial profile through the right-hand edge; the nozzle sector is at
    # the top or bottom, so angle zero is always outside it.
    radii = np.linspace(radius_bin + search, radius_bin - search, 2 * search + 1)
    profile = _sample_radial_profiles(
        image_gray,
        x_bin,
        y_bin,
        np.asarray([0.0]),
        radii,
    )[0]
    inner = max(3, profile.size // 8)
    background = float(np.median(profile[:inner]))
    foreground = float(np.median(profile[-inner:]))
    span = foreground - background
    crossings: dict[float, float] = {}
    if span > 0:
        for fraction in (0.2, 0.5, 0.8):
            crossing = _first_upward_crossing(
                profile, background + fraction * span
            )
            if crossing is not None:
                crossings[fraction] = float(
                    np.interp(crossing, np.arange(profile.size), radii)
                )

    plt = _pyplot()
    style = {
        "font.family": "Arial",
        "font.size": 8.0,
        "text.color": "#222222",
        "axes.labelcolor": "#222222",
        "axes.edgecolor": "#444444",
        "axes.linewidth": 0.6,
        "xtick.color": "#222222",
        "ytick.color": "#222222",
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
    with plt.rc_context(style):
        figure, axes = plt.subplots(
            2,
            2,
            figsize=(184.0 / 25.4, 150.0 / 25.4),
            constrained_layout=True,
        )

        if image_color is not None:
            color = np.asarray(image_color)
            if color.ndim == 3 and color.shape[2] >= 3:
                image_rgb = color[..., 2::-1]
            else:
                image_rgb = image_gray
        else:
            image_rgb = image_gray

        height, width = image_gray.shape
        ax = axes[0, 0]
        ax.imshow(
            image_rgb,
            cmap=None if image_rgb.ndim == 3 else "gray",
            interpolation="antialiased",
        )
        ax.add_patch(
            Circle(
                (x_bin, y_bin),
                radius_bin,
                fill=False,
                edgecolor="#D55E00",
                linewidth=1.0,
                linestyle=(0, (4, 2)),
                label="binary circle",
            )
        )
        ax.add_patch(
            Circle(
                (x_sub, y_sub),
                radius_sub,
                fill=False,
                edgecolor="#009E73",
                linewidth=1.2,
                label="sub-pixel fit",
            )
        )
        ax.set_xlim(0, width)
        ax.set_ylim(height, 0)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title("raw frame", fontsize=8)
        ax.legend(loc="upper right", fontsize=6.5, frameon=True)

        ax = axes[0, 1]
        ax.imshow(mask, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        ax.add_patch(
            Circle(
                (x_bin, y_bin),
                radius_bin,
                fill=False,
                edgecolor="#D55E00",
                linewidth=1.0,
                linestyle=(0, (4, 2)),
            )
        )
        ax.set_xlim(0, width)
        ax.set_ylim(height, 0)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title("foreground mask", fontsize=8)

        # Keep enough source pixels around the sphere for a high-resolution
        # printed crop while still showing the nozzle-side gap in the points.
        half = max(128, int(round(3.8 * radius_bin)))
        x0 = max(0, int(round(x_bin)) - half)
        x1 = min(width, int(round(x_bin)) + half)
        y0 = max(0, int(round(y_bin)) - half)
        y1 = min(height, int(round(y_bin)) + half)
        crop = image_rgb[y0:y1, x0:x1]
        ax = axes[1, 0]
        ax.imshow(
            crop,
            cmap=None if crop.ndim == 3 else "gray",
            interpolation="antialiased",
        )
        ax.add_patch(
            Circle(
                (x_bin - x0, y_bin - y0),
                radius_bin,
                fill=False,
                edgecolor="#D55E00",
                linewidth=1.0,
                linestyle=(0, (4, 2)),
            )
        )
        ax.add_patch(
            Circle(
                (x_sub - x0, y_sub - y0),
                radius_sub,
                fill=False,
                edgecolor="#009E73",
                linewidth=1.2,
            )
        )
        if sub_x.size:
            ax.scatter(
                sub_x - x0,
                sub_y - y0,
                s=4.0,
                c="#F0E442",
                edgecolors="#333333",
                linewidths=0.15,
                zorder=3,
                label="50 % crossings",
            )
        ax.set_xlim(0, x1 - x0)
        ax.set_ylim(y1 - y0, 0)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"edge points (n = {sub_x.size})", fontsize=8)
        ax.legend(loc="upper right", fontsize=6.5, frameon=True)

        ax = axes[1, 1]
        offset = radius_bin - radii
        ax.plot(offset, profile, color="#0072B2", linewidth=1.0)
        ax.axvline(
            0.0,
            color="#D55E00",
            linewidth=0.9,
            linestyle=(0, (4, 2)),
            label="binary edge",
        )
        for fraction, line_color, linestyle in (
            (0.2, "#999999", ":"),
            (0.8, "#999999", ":"),
            (0.5, "#009E73", "-"),
        ):
            if fraction in crossings:
                crossing_offset = radius_bin - crossings[fraction]
                ax.axvline(
                    crossing_offset,
                    color=line_color,
                    linewidth=0.9,
                    linestyle=linestyle,
                    label=(
                        "50 % crossing"
                        if fraction == 0.5
                        else "20/80 % crossings" if fraction == 0.2 else None
                    ),
                )
        if 0.5 in crossings:
            crossing_offset = radius_bin - crossings[0.5]
            ax.plot(
                [crossing_offset],
                [background + 0.5 * span],
                "o",
                color="#009E73",
                markersize=3.0,
                zorder=4,
            )
        ax.set_xlim(-search - 1, search + 1)
        ax.set_xlabel("offset from binary edge (px)")
        ax.set_ylabel("intensity (DN)")
        ax.set_title("radial profile at 0$^\\circ$", fontsize=8)
        ax.grid(True, color="#DDDDDD", linewidth=0.4, alpha=0.7)
        ax.legend(loc="lower right", fontsize=6.5, frameon=True)

        for panel_ax, label in zip(axes.flat, ("a", "b", "c", "d")):
            panel_ax.text(
                -0.03,
                1.02,
                f"({label})",
                transform=panel_ax.transAxes,
                fontsize=8,
                fontweight="bold",
                va="bottom",
                ha="right",
            )

        debug_folder.mkdir(parents=True, exist_ok=True)
        pdf_path = debug_folder / f"{filename}.pdf"
        figure.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)
        figure.savefig(
            debug_folder / f"{filename}.png",
            dpi=dpi,
            bbox_inches="tight",
            pad_inches=0.02,
        )
        plt.close(figure)
    return pdf_path


def visualize_validation(
    *,
    binary_blur: np.ndarray,
    binary_diameter: np.ndarray,
    subpixel_blur: np.ndarray,
    subpixel_diameter: np.ndarray,
    pair_labels: Sequence[str],
    pair_binary_spread_um: np.ndarray,
    pair_subpixel_spread_um: np.ndarray,
    residual_components: np.ndarray,
    residual_rmse: float,
    radial_radius: np.ndarray,
    radial_scale: np.ndarray,
    radial_observed_radius: np.ndarray | None,
    radial_observed_scale: np.ndarray | None,
    debug_folder: Path,
    filename: str = "fig4",
    reference_diameter: float | None = None,
    reference_tolerance: float | None = None,
    dpi: int = 300,
) -> Path:
    """Render the four-panel validation figure for the software paper.

    The panels show the defocus dependence of the binary and sub-pixel
    diameters, the diameter repeatability of repeated sphere scans, a normal
    quantile--quantile plot of the reprojection residuals, and the fitted
    radial-scale profile.  The function only consumes measured arrays; the
    dataset selection and the calibration fits live in the caller.
    """
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter, NullFormatter
    from statistics import NormalDist

    binary_blur = np.asarray(binary_blur, dtype=float).reshape(-1)
    binary_diameter = np.asarray(binary_diameter, dtype=float).reshape(-1)
    subpixel_blur = np.asarray(subpixel_blur, dtype=float).reshape(-1)
    subpixel_diameter = np.asarray(subpixel_diameter, dtype=float).reshape(-1)
    pair_labels = list(pair_labels)
    pair_binary_spread_um = np.asarray(
        pair_binary_spread_um, dtype=float
    ).reshape(-1)
    pair_subpixel_spread_um = np.asarray(
        pair_subpixel_spread_um, dtype=float
    ).reshape(-1)
    residual_components = np.asarray(
        residual_components, dtype=float
    ).reshape(-1)
    radial_radius = np.asarray(radial_radius, dtype=float).reshape(-1)
    radial_scale = np.asarray(radial_scale, dtype=float).reshape(-1)
    if radial_observed_radius is not None:
        radial_observed_radius = np.asarray(
            radial_observed_radius, dtype=float
        ).reshape(-1)
    if radial_observed_scale is not None:
        radial_observed_scale = np.asarray(
            radial_observed_scale, dtype=float
        ).reshape(-1)

    if binary_blur.size != binary_diameter.size:
        raise ValueError("binary_blur and binary_diameter must have equal size")
    if subpixel_blur.size != subpixel_diameter.size:
        raise ValueError(
            "subpixel_blur and subpixel_diameter must have equal size"
        )
    if not (
        len(pair_labels)
        == pair_binary_spread_um.size
        == pair_subpixel_spread_um.size
    ):
        raise ValueError("pair labels and pair spreads must have equal size")
    if residual_components.size == 0 or residual_components.size % 2:
        raise ValueError(
            "residual_components must contain x/y residual pairs"
        )
    if radial_radius.size != radial_scale.size or radial_radius.size < 2:
        raise ValueError(
            "radial_radius and radial_scale must have equal non-zero size"
        )
    if (radial_observed_radius is None) != (radial_observed_scale is None):
        raise ValueError(
            "radial observed radius and scale must be supplied together"
        )
    if (reference_diameter is None) != (reference_tolerance is None):
        raise ValueError(
            "reference_diameter and reference_tolerance must be supplied "
            "together"
        )
    if np.any(pair_binary_spread_um <= 0) or np.any(
        pair_subpixel_spread_um <= 0
    ):
        raise ValueError("pair spreads must be positive for the log axis")

    binary_color = "#D55E00"
    subpixel_color = "#0072B2"
    reference_fill = "#D9F0E5"
    reference_line = "#009E73"
    radial_color = "#CC79A7"
    ink = "#222222"
    grid = "#E3E3E3"

    style = {
        "font.family": "Arial",
        "font.size": 8.0,
        "text.color": ink,
        "axes.labelcolor": ink,
        "axes.edgecolor": "#444444",
        "axes.linewidth": 0.6,
        "axes.titlecolor": ink,
        "xtick.color": ink,
        "ytick.color": ink,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 6.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }

    plt = _pyplot()
    with plt.rc_context(style):
        figure, axes = plt.subplots(
            2,
            2,
            figsize=(184.0 / 25.4, 150.0 / 25.4),
            constrained_layout=True,
        )

        # (a) diameter versus edge blur
        ax = axes[0, 0]
        if reference_diameter is not None and reference_tolerance is not None:
            low = reference_diameter - reference_tolerance
            high = reference_diameter + reference_tolerance
            ax.axhspan(
                low,
                high,
                facecolor=reference_fill,
                edgecolor=reference_line,
                linewidth=0.5,
                zorder=0,
            )
            ax.axhline(
                reference_diameter,
                color=reference_line,
                linewidth=0.8,
                zorder=1,
            )
        ax.scatter(
            binary_blur,
            binary_diameter,
            s=7.0,
            color=binary_color,
            alpha=0.42,
            linewidths=0,
            zorder=2,
        )
        ax.scatter(
            subpixel_blur,
            subpixel_diameter,
            s=7.0,
            color=subpixel_color,
            alpha=0.42,
            linewidths=0,
            zorder=2,
        )

        binary_slope, binary_intercept = np.polyfit(
            binary_blur, binary_diameter, 1
        )
        subpixel_slope, subpixel_intercept = np.polyfit(
            subpixel_blur, subpixel_diameter, 1
        )
        binary_corr = float(np.corrcoef(binary_blur, binary_diameter)[0, 1])
        subpixel_corr = float(
            np.corrcoef(subpixel_blur, subpixel_diameter)[0, 1]
        )
        x_binary = np.linspace(0.0, binary_blur.max(), 80)
        x_subpixel = np.linspace(
            0.0, subpixel_blur.max(), 80
        )
        ax.plot(
            x_binary,
            binary_slope * x_binary + binary_intercept,
            color=binary_color,
            linewidth=1.1,
            zorder=3,
        )
        ax.plot(
            x_subpixel,
            subpixel_slope * x_subpixel + subpixel_intercept,
            color=subpixel_color,
            linewidth=1.1,
            zorder=3,
        )

        handles: list[Line2D | Patch] = [
            Line2D(
                [0],
                [0],
                color=binary_color,
                marker="o",
                markersize=3.0,
                linewidth=1.1,
                label=(
                    f"binary: {binary_slope * 1000:+.1f} "
                    f"\u00b5m/px (r={binary_corr:.2f})"
                ),
            ),
            Line2D(
                [0],
                [0],
                color=subpixel_color,
                marker="o",
                markersize=3.0,
                linewidth=1.1,
                label=(
                    f"sub-pixel: {subpixel_slope * 1000:+.1f} "
                    f"\u00b5m/px (r={subpixel_corr:.2f})"
                ),
            ),
        ]
        if reference_diameter is not None and reference_tolerance is not None:
            handles.append(
                Patch(
                    facecolor=reference_fill,
                    edgecolor=reference_line,
                    label=(
                        f"{reference_diameter:.3f} \u00b1 "
                        f"{reference_tolerance:.3f} mm"
                    ),
                )
            )
        ax.legend(
            handles=handles,
            loc="upper left",
            frameon=False,
            handlelength=1.8,
            borderaxespad=0.3,
        )
        all_diameters = np.concatenate((binary_diameter, subpixel_diameter))
        margin = 0.03 * float(np.ptp(all_diameters))
        y_low = float(all_diameters.min()) - margin
        y_high = float(all_diameters.max()) + margin
        if reference_diameter is not None and reference_tolerance is not None:
            y_low = min(y_low, reference_diameter - reference_tolerance)
            y_high = max(y_high, reference_diameter + reference_tolerance)
        ax.set_ylim(y_low, y_high)
        ax.set_xlim(0.0, max(binary_blur.max(), subpixel_blur.max()) * 1.04)
        ax.set_xlabel("edge blur \u03c3 (px)")
        ax.set_ylabel("apparent diameter (mm)")
        ax.set_title("1 mm ceramic sphere", fontsize=8, loc="left")
        ax.grid(axis="y", color=grid, linewidth=0.5)
        ax.set_axisbelow(True)

        # (b) diameter repeatability
        ax = axes[0, 1]
        positions = np.arange(len(pair_labels), dtype=float)
        for index, (binary_value, subpixel_value) in enumerate(
            zip(pair_binary_spread_um, pair_subpixel_spread_um, strict=True)
        ):
            ax.plot(
                [binary_value, subpixel_value],
                [index, index],
                color="#BBBBBB",
                linewidth=1.2,
                zorder=1,
            )
            ax.scatter(
                [binary_value],
                [index],
                s=24,
                color=binary_color,
                zorder=2,
            )
            ax.scatter(
                [subpixel_value],
                [index],
                s=24,
                marker="s",
                color=subpixel_color,
                zorder=2,
            )
            ax.text(
                max(binary_value, subpixel_value) * 1.12,
                index,
                f"{binary_value:.1f} / {subpixel_value:.1f}",
                va="center",
                ha="left",
                fontsize=6.5,
                color=ink,
            )
        ax.set_xscale("log")
        ax.set_xlim(1.0, 100.0)
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda value, _: f"{value:g}")
        )
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_yticks(positions, pair_labels)
        ax.invert_yaxis()
        ax.set_xlabel(
            "diameter repeatability, max\u2212min (\u00b5m, log)"
        )
        ax.set_title("same sphere, independent scans", fontsize=8, loc="left")
        ax.grid(axis="x", color=grid, linewidth=0.5)
        ax.set_axisbelow(True)
        ax.legend(
            handles=[
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    color="none",
                    markerfacecolor=binary_color,
                    markeredgecolor=binary_color,
                    markersize=4.0,
                    label="binary",
                ),
                Line2D(
                    [0],
                    [0],
                    marker="s",
                    color="none",
                    markerfacecolor=subpixel_color,
                    markeredgecolor=subpixel_color,
                    markersize=4.0,
                    label="sub-pixel",
                ),
            ],
            loc="upper right",
            frameon=False,
        )

        # (c) normal quantile-quantile plot of residual components
        ax = axes[1, 0]
        residual_xy = residual_components.reshape(-1, 2)
        standardized = []
        for column in residual_xy.T:
            column_std = float(np.std(column, ddof=1))
            if column_std > 0:
                standardized.append((column - column.mean()) / column_std)
        if not standardized:
            raise ValueError("residual components have zero variance")
        standardized_residuals = np.sort(
            np.concatenate(standardized)
        )
        n_residuals = standardized_residuals.size
        normal = NormalDist()
        theoretical = np.asarray(
            [
                normal.inv_cdf((index + 0.5) / n_residuals)
                for index in range(n_residuals)
            ]
        )
        ax.scatter(
            theoretical,
            standardized_residuals,
            s=5.0,
            color="#4D4D4D",
            alpha=0.65,
            linewidths=0,
        )
        limit = 1.05 * float(
            max(
                np.max(np.abs(theoretical)),
                np.max(np.abs(standardized_residuals)),
            )
        )
        ax.plot(
            [-limit, limit],
            [-limit, limit],
            color=binary_color,
            linewidth=0.9,
            linestyle=(0, (3, 2)),
        )
        ax.set_xlim(-limit, limit)
        ax.set_ylim(-limit, limit)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("theoretical normal quantile")
        ax.set_ylabel("standardized residual")
        ax.set_title("2 mm reprojection residuals", fontsize=8, loc="left")
        ax.text(
            0.03,
            0.97,
            f"RMSE = {residual_rmse:.2f} px\nn = {n_residuals}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=6.8,
            color=ink,
        )
        ax.grid(color=grid, linewidth=0.5)
        ax.set_axisbelow(True)

        # (d) fitted radial-scale profile
        ax = axes[1, 1]
        scale_percent = (radial_scale - 1.0) * 100.0
        ax.axhline(0.0, color="#888888", linewidth=0.7)
        ax.plot(
            radial_radius,
            scale_percent,
            color=radial_color,
            linewidth=1.3,
        )
        if (
            radial_observed_radius is not None
            and radial_observed_scale is not None
        ):
            observed_percent = (radial_observed_scale - 1.0) * 100.0
            ax.scatter(
                radial_observed_radius,
                observed_percent,
                s=16,
                facecolors="white",
                edgecolors=radial_color,
                linewidths=0.8,
                zorder=3,
                label="observed quantiles",
            )
            ax.legend(loc="lower left", frameon=False)
        radial_low = float(scale_percent.min())
        radial_high = float(scale_percent.max())
        radial_span = max(radial_high - radial_low, 0.02)
        ax.set_xlim(0.0, float(radial_radius.max()) * 1.02)
        ax.set_ylim(
            radial_low - 0.12 * radial_span,
            radial_high + 0.12 * radial_span,
        )
        ax.set_xlabel("normalized image radius")
        ax.set_ylabel("radial-scale change (%)")
        ax.set_title("2.381 mm POM radial scale", fontsize=8, loc="left")
        ax.text(
            0.97,
            0.95,
            f"range = {radial_high - radial_low:.2f} %",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=6.8,
            color=ink,
        )
        ax.grid(color=grid, linewidth=0.5)
        ax.set_axisbelow(True)

        for column_index, ax in enumerate(axes.flat):
            panel_label = "abcd"[column_index]
            x_pos = -0.12 if column_index % 2 == 0 else -0.075
            ax.text(
                x_pos,
                1.03,
                f"({panel_label})",
                transform=ax.transAxes,
                ha="left",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
                color=ink,
                clip_on=False,
            )

        debug_folder = Path(debug_folder)
        debug_folder.mkdir(parents=True, exist_ok=True)
        pdf_path = debug_folder / f"{filename}.pdf"
        figure.savefig(
            pdf_path,
            format="pdf",
            facecolor="white",
            bbox_inches="tight",
            pad_inches=0.04,
        )
        figure.savefig(
            debug_folder / f"{filename}.png",
            format="png",
            dpi=dpi,
            facecolor="white",
            bbox_inches="tight",
            pad_inches=0.04,
        )
        plt.close(figure)
    return pdf_path


def visualize_results(rel_robot_positions: np.ndarray,
                      center_points_adjusted: np.ndarray,
                      extrinsic_matrix: np.ndarray,
                      intrinsic_matrix: np.ndarray,
                      radii: np.ndarray,
                      sigmas: np.ndarray,
                      image_size_xy: tuple[int, int],
                      back_projected_home_pos: np.ndarray,
                      closest_image_arg: int,
                      n_distortion_coefs: int,
                      debug_nozzle_and_home_pos: dict,
                      residuals: np.ndarray,
                      all_debug_data_to_store: list[list[str | float | np.floating | np.integer]],
                      debug_folder: Path) -> None:
    visualize_radii(
        rel_robot_positions,
        extrinsic_matrix,
        radii=radii,
        sigmas=sigmas,
        debug_folder=debug_folder,
    )

    visualize_sigmas(
        rel_robot_positions,
        extrinsic_matrix,
        sigmas=sigmas,
        debug_folder=debug_folder,
    )

    visualize_image_center_points(
        center_points_adjusted,
        sigmas,
        image_size_xy=image_size_xy,
        camera_principal_point=intrinsic_matrix[:2, 2],
        nozzle_home_pos=back_projected_home_pos,
        closest_image_arg=closest_image_arg,
        n_distortion_coefs=n_distortion_coefs,
        debug_folder=debug_folder,
    )

    visualize_nozzle_and_home_pos_estimation(
        debug_nozzle_and_home_pos,
        debug_folder=debug_folder
    )

    visualize_residuals(
        residuals,
        center_points_adjusted,
        debug_folder=debug_folder,
        image_size_xy=image_size_xy,
    )

    visualize_debug_data(
        all_debug_data_to_store,
        debug_folder = debug_folder,
    )
