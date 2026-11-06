# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Functions to visualize results."""

from pathlib import Path

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
    plt.savefig(debug_folder / f'radii_in_depth.png')
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
    plt.savefig(debug_folder / f'sigmas_in_depth.png')
    plt.close()


def visualize_diff_new_old_center_points():
    pass


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
    plt.savefig(debug_folder / f'scale_coef_estimation.png')
    plt.close()


def visualize_n_sigma_estimation(n_sigmas: np.ndarray,
                                 std_radii: np.ndarray,
                                 debug_folder: Path) -> None:

    apply_own_style_to_mpl()
    plt = _pyplot()

    plt.plot(n_sigmas, std_radii)

    plt.xlabel("n_sigma (px)")
    plt.ylabel("std_radii (px)")

    plt.tight_layout()
    plt.savefig(debug_folder / f'n_sigma_estimation.png')
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
    plt.savefig(debug_folder / f'sphere_diam_estimation.png')
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
    plt.savefig(debug_folder / f'sphere_diam_vs_depth.png')
    plt.close()

    diam = np.polyval(popt, 0)
    plt.scatter(z_pos, (est_radii-diam)/diam*100)


    plt.xlabel("rel. z-depth (mm)")
    plt.ylabel("sphere diameter rel. error (%)")

    plt.tight_layout()
    plt.savefig(debug_folder / f'sphere_diam_rel_error_vs_depth.png')
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
    plt.ylabel(f"Focal length (px)")

    plt.legend()
    plt.tight_layout()
    plt.savefig(debug_folder / f'focal length vs number of points.png')
    plt.close()

    plt.errorbar(values[1], values[2], yerr=values[3], label=names[2])
    plt.errorbar(values[1], values[4], yerr=values[5], label=names[4])
    plt.xlabel(f"{names[1]}")
    plt.ylabel(f"Focal length (px)")

    plt.legend()
    plt.tight_layout()
    plt.savefig(debug_folder / f'focal length vs left number of points.png')
    plt.close()

    plt.errorbar(values[0], values[6], yerr=values[7], label=names[6])
    plt.xlabel(f"{names[0]}")
    plt.ylabel(f"{names[6]} (mm)")

    plt.tight_layout()
    plt.savefig(debug_folder / f'camera distance vs number of points.png')
    plt.close()

    plt.errorbar(values[1], values[6], yerr=values[7], label=names[6])
    plt.xlabel(f"{names[1]}")
    plt.ylabel(f"{names[6]} (mm)")

    plt.tight_layout()
    plt.savefig(debug_folder / f'camera distance vs left number of points.png')
    plt.close()


    plt.plot(values[0], values[-1], label=names[0])
    plt.plot(values[1], values[-1], label=names[1])
    plt.xlabel(f"{names[0]}")
    plt.ylabel(f"{names[-1]}")

    plt.legend()
    plt.tight_layout()
    plt.savefig(debug_folder / f'RMSE vs number of points.png')
    plt.close()


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
