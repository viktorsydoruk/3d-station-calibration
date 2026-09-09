"""Functions to visualize results"""

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt
from pathlib import Path


def apply_own_style_to_mpl(font_size: float = 8) -> None:
    """Applying a specific style for plotting TODO put here all the styles that should be modified"""
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
                                  infinity_point: np.ndarray | None,
                                  n_distortion_coefs: int,
                                  debug_folder: Path) -> None:
    apply_own_style_to_mpl()

    plt.scatter(center_points[:, 0], center_points[:, 1], c=sigmas)
    plt.colorbar()

    # showing camera principal_point
    plt.axvline(camera_principal_point[0], c='tab:red', linestyle='--', alpha=0.5)
    plt.axhline(camera_principal_point[1], c='tab:red', linestyle='--', alpha=0.5)

    if infinity_point is not None:
        plt.scatter(*infinity_point, c='tab:red')

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
