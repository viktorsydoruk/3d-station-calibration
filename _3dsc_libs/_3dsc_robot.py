"""Functions related to robotic arm position calculations"""
import cv2
import numpy as np
from typing import Any


def find_robot_home_pos_shift(robot_positions: np.ndarray,
                              image_center_points: np.ndarray,
                              intrinsic_matrix: np.ndarray,
                              extrinsic_matrix: np.ndarray,
                              distortion: np.ndarray,
                              sigmas: np.ndarray) -> np.ndarray:
    """Estimation of the shift of the robotic arm home position based on sigma, cx and cy"""
    # converting the robotic arm positions into the camera coordinate system
    coords = np.dot(extrinsic_matrix[None, :3, :3], robot_positions[:, :, None])[0, :, :, 0]
    # taking the distortion into account for the images center points
    image_center_points_undist = cv2.undistortImagePoints(image_center_points, intrinsic_matrix, distortion)[:, 0]

    # initialization
    d_home_pos = np.zeros(3, dtype=float)
    x_coords, y_coords, z_coords = coords
    x_im_coords, y_im_coords = image_center_points_undist.T
    r_from_c_xy = np.sqrt(x_coords**2 + y_coords**2)

    # z shift estimation using sigma of the blured edges
    popt = np.polyfit(z_coords, sigmas, deg=4, w=1/(r_from_c_xy**2+sigmas**2))
    x = np.linspace(np.min(z_coords), np.max(z_coords), 101)
    y = np.polyval(popt, x)
    d_home_pos[2] = x[np.argmin(y)]

    # x shift estimation using cx
    popt = np.polyfit(x_im_coords, x_coords, deg=1, w=1/sigmas**2)
    d_home_pos[0] = np.polyval(popt, intrinsic_matrix[0, 2])

    # y shift estimation using cy
    popt = np.polyfit(y_im_coords, y_coords, deg=1, w=1/sigmas**2)
    d_home_pos[1] = np.polyval(popt, intrinsic_matrix[1, 2])

    # converting back to the robotic coordinate system
    d_home_pos = np.dot(extrinsic_matrix[:3, :3].T, d_home_pos[:, None]).T[0]
    return d_home_pos


def get_nozzle_end_home_position(sphere_home_position: np.ndarray,
                                 robot_positions: np.ndarray,
                                 image_center_points: np.ndarray,
                                 intrinsic_matrix: np.ndarray,
                                 extrinsic_matrix: np.ndarray,
                                 distortion: np.ndarray,
                                 sigmas: np.ndarray,
                                 radii: np.ndarray,
                                 all_directions: np.ndarray) -> tuple[np.ndarray, float, dict[str, dict[str, Any]]]:
    """Estimation of the shift of the robotic arm home position based on sigma, cx and cy"""
    debug_info = {}

    # converting the robotic arm positions into the camera coordinate system
    robot_camera_coords = np.dot(extrinsic_matrix[None, :3, :3], robot_positions[:, :, None])[0, :, :, 0]
    # taking the distortion into account for the images center points
    image_center_points_undist = cv2.undistortImagePoints(image_center_points, intrinsic_matrix, distortion)[:, 0]

    px = np.sqrt(np.sum((image_center_points_undist - intrinsic_matrix[:2, 2][None, :])**2, axis=1))
    mm = np.sqrt(np.sum(robot_camera_coords[:2]**2, axis=0))

    mask = mm > np.max(mm) / 2

    popt = np.polyfit(robot_camera_coords[2][mask], mm[mask]/px[mask], deg=2)
    debug_info['scaling_visualization'] = {
        'z_pos': robot_camera_coords[2][mask],
        'scale': mm[mask]/px[mask],
        'fit_popt': popt,
    }

    coef_for_radii = np.polyval(popt, robot_camera_coords[2])

    n_sigmas = np.linspace(0, 4, 100)
    std_radii = np.asarray([np.std(2*(radii-sel_n_sigma*sigmas)*coef_for_radii) for sel_n_sigma in n_sigmas])
    n_sigma_est = n_sigmas[np.argmin(std_radii)]

    debug_info['n_sigma_estimation'] = {
        'n_sigmas': n_sigmas,
        'std_radii': std_radii,
    }

    sphere_radius = np.mean((radii-n_sigma_est*sigmas)*coef_for_radii)

    debug_info['sphere_radius_estimation'] = {
        'z_pos': robot_camera_coords[2],
        'radii': radii,
        'sigmas': sigmas,
        'coef_for_radii': coef_for_radii,
        'n_sigma_est' : n_sigma_est,

    }

    debug_info['sphere_radius_vs_depth'] = {
        'z_pos': robot_camera_coords[2],
        'radii': radii,
        'sigmas': sigmas,
        'coef_for_radii': np.polyval(popt, 0),
        'n_sigma_est' : n_sigma_est,

    }

    sign = np.sign(np.mean(all_directions.astype(float)))
    # getting the nozzle end home position in camera coordinate system
    nozzle_end_home_position = np.dot(extrinsic_matrix[:3, :3], sphere_home_position[:, None]).T[0] + [0, sign*sphere_radius, 0]

    # converting the nozzle end home position to the robotic arm coordinate system
    nozzle_end_home_position = np.dot(extrinsic_matrix[:3, :3].T, nozzle_end_home_position[:, None]).T[0]
    return nozzle_end_home_position, n_sigma_est, debug_info