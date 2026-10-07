"""Function to estimate camera intrinsics and robot -> camera extrinsics"""

__all__ = ["print_calibration", "get_calibration", "calibrate_camera", "check_distortion_monotonicity",
           "back_projected_point", "calculate_RMSE", "calculate_calibration_errors"]

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.optimize import OptimizeResult

from ._3dsc_support import fit_line_general_form, intersect_lines, calculate_errors


def estimate_r_initial(robot_positions: np.ndarray,
                       image_center_points: np.ndarray,
                       radii: np.ndarray,
                       sigmas: np.ndarray) -> np.ndarray:
    """
        Estimation of initial robot-camera rotation matrix using positions of robotic arm and center points on images

        ChatGPT generated such a constant:
        ============================================================
        Robot -> camera initial rotation

        Robot:
          +X = toward camera
          +Y = right in image
          +Z = up in image

        OpenCV camera:
          +X = right
          +Y = down
          +Z = away from camera

        Therefore:

          Xc =  Yr
          Yc =  Zr
          Zc = -Xr
        ============================================================
        R_INITIAL = np.array([
            [0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0],
            [-1.0, 0.0, 0.0],
        ], dtype=np.float64)

    :param robot_positions: positions of a nozzle by robotic arm
    :param image_center_points: center points of spheres on the images
    :param radii: radii of spheres
    :param sigmas: bluring sigmas of spheres edges
    :return: 3x3 rotation matrix
    """
    camera_points = np.asarray([*image_center_points.T, -(radii-2*sigmas)]).T

    # just use correlation coef as r_initial
    r_initial = np.corrcoef(camera_points.T, robot_positions.T)[:3, 3:]

    return r_initial


def extract_z_lines(robot_positions: np.ndarray,
                    image_center_points: np.ndarray,
                    r_initial: np.ndarray) -> np.ndarray:
    z_arg = np.argwhere(r_initial[2] != 0)[0][0]
    left_args = [0, 1, 2]
    left_args.remove(z_arg)

    lines = []
    left_robot_positions = np.copy(robot_positions)
    left_image_center_points = np.copy(image_center_points)
    while len(left_robot_positions) != 0:
        sel_args = np.argwhere((left_robot_positions[:, left_args[0]] == left_robot_positions[0, left_args[0]])
                               & (left_robot_positions[:, left_args[1]] == left_robot_positions[0, left_args[1]])).flatten()
        if len(sel_args) > 3:
            a, b, c = fit_line_general_form(*left_image_center_points[sel_args].T)

            lines.append([a, b, c])
        left_robot_positions = np.delete(left_robot_positions, sel_args, axis=0)
        left_image_center_points = np.delete(left_image_center_points, sel_args, axis=0)

    all_intersection_points = []
    for i in range(len(lines)):
        for j in range(i, len(lines)):
            int_point = intersect_lines(*lines[i], *lines[j])
            if int_point is not None and int_point[0] > 0 and int_point[1] > 0 and int_point[0] < 2500 and int_point[1] < 2000:
                all_intersection_points.append(int_point)

    all_intersection_points = np.array(all_intersection_points)
    return np.mean(all_intersection_points, axis=0)


def make_initial_parameters(focal_length: float = 2000.0,
                            camera_distance: float = 80.0,
                            image_size: tuple = (2500, 2000),
                            fix_cx_cy: bool = False,
                            n_distortion_coefs: int = 5,
                            r_initial: np.ndarray = np.eye(3)) -> np.ndarray:
    """
        Create initial parameter vector.

        camera_distance is only used as an approximate initial
        translation. It may need adjustment depending on the
        robot coordinate origin.

    :param focal_length:
    :param camera_distance:
    :param image_size:
    :param fix_cx_cy:
    :param n_distortion_coefs:
    :param r_initial:
    :return:
    """

    params = np.empty(0, dtype=np.float64)

    # intrinsics
    params = np.append(params, (focal_length, focal_length))  # fx and fy
    if not fix_cx_cy:
        params = np.append(params, (image_size[0] / 2, image_size[1] / 2))  # cx, cy if needed

    # distortion
    params = np.append(params, (0,) * n_distortion_coefs)

    # initial rotation
    rvecs_initial, _ = cv2.Rodrigues(r_initial)
    params = np.append(params, rvecs_initial.ravel())

    # initial translation
    params = np.append(params, (0, 0, camera_distance))

    return params


def unwrap_params(params: np.ndarray,
                  image_size: tuple = (2500, 2000),
                  fix_cx_cy: bool = False,
                  n_distortion_coefs: int = 5) -> tuple[float , float, float, float, np.ndarray, np.ndarray, np.ndarray]:
    """Unwrapping the parameters for least-square problem"""
    _end_arg = 0
    fx, fy = params[_end_arg:_end_arg + 2]
    _end_arg += 2

    if not fix_cx_cy:
        cx, cy = params[_end_arg:_end_arg + 2]
        _end_arg += 2
    else:
        cx = image_size[0] / 2
        cy = image_size[1] / 2

    distortion = np.zeros(14, dtype=np.float64)
    distortion[:n_distortion_coefs] = params[_end_arg:_end_arg + n_distortion_coefs]
    _end_arg += n_distortion_coefs

    rvec = params[_end_arg:_end_arg + 3]
    _end_arg += 3

    tvec = params[_end_arg:_end_arg + 3]
    _end_arg += 3

    return fx, fy, cx, cy, distortion, rvec, tvec


def unwrap_k_distortion_params(params: np.ndarray,
                               fix_cx_cy: bool = False,
                               n_distortion_coefs: int = 5) -> np.ndarray:
    """Unwrapping the distortion parameters"""
    _end_arg = 2

    if not fix_cx_cy:
        _end_arg += 2

    distortion = np.zeros(14, dtype=np.float64)
    distortion[:n_distortion_coefs] = params[_end_arg:_end_arg + n_distortion_coefs]

    return distortion


def check_distortion_monotonicity(distortion: np.ndarray,
                                  intrinsic_matrix: np.ndarray,
                                  image_size_xy: tuple = (2500, 2000),
                                  ) -> bool:
    """
        Checking the monotonic behaviour of distortion function 1 + k1*r**2 + k2*r**4 + k3*r**6
    :param distortion: distortion vector
    :param intrinsic_matrix: intrinsic matrix
    :param image_size_xy: image size (x, y)
    :return: boolean value
    """
    # defining the max related radius and related radius values
    r_max = np.sqrt((image_size_xy[0] / 2) ** 2 + (image_size_xy[1] / 2) ** 2) / intrinsic_matrix[0, 0]
    r_val = np.linspace(0, r_max, 101)

    # calculating
    func_val = 1 + distortion[0] * r_val ** 2 + distortion[1] * r_val ** 4 + distortion[4] * r_val ** 6
    dfunc_val = np.diff(func_val)
    return np.all(dfunc_val >= 0) or np.all(dfunc_val <= 0)


def params_names(fix_cx_cy: bool = False,
                 n_distortion_coefs: int = 5) -> list[str]:
    """Unwrapping the parameters for least-square problem"""
    all_names = ["fx", "fy"]

    if not fix_cx_cy:
        all_names += ["cx", "cy"]

    all_names += ["k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6", "s1", "s2", "s3", "s4", "τx", "τy"][:n_distortion_coefs]
    all_names += ["r1", "r2", "r3", "t1", "t2", "t3"]

    return all_names


def project_points(params: np.ndarray,
                   robot_points: np.ndarray,
                   image_size: tuple = (2500, 2000),
                   fix_cx_cy: bool = False,
                   n_distortion_coefs: int = 5) -> np.ndarray:
    """
        Transform robot coordinates to camera coordinates and project them into the image.
    :param params:
    :param robot_points:
    :param image_size:
    :param fix_cx_cy:
    :param n_distortion_coefs:
    :return:
    """
    fx, fy, cx, cy, distortion, rvec, tvec = unwrap_params(
        params,
        image_size,
        fix_cx_cy,
        n_distortion_coefs
    )

    camera_matrix = np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)

    projected, _ = cv2.projectPoints(
        robot_points,
        rvec,
        tvec,
        camera_matrix,
        distortion
    )

    return projected.reshape(-1, 2)


def residuals(params: np.ndarray,
              robot_points: np.ndarray,
              measured_image_points: np.ndarray,
              image_size: tuple = (2500, 2000),
              fix_cx_cy: bool = False,
              n_distortion_coefs: int = 5) -> np.ndarray:
    """
        Return x/y reprojection error for all measurements.
    :param params:
    :param robot_points:
    :param measured_image_points:
    :param image_size:
    :param fix_cx_cy:
    :param n_distortion_coefs:
    :return:
    """

    predicted = project_points(
        params,
        robot_points,
        image_size=image_size,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )

    error = predicted - measured_image_points

    return np.ravel(error)


def get_calibration(params: np.ndarray,
                    image_size_xy: tuple = (2500, 2000),
                    fix_cx_cy: bool = False,
                    n_distortion_coefs: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:

    fx, fy, cx, cy, distortion, rot_vec, tra_vec = unwrap_params(
        params,
        image_size=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )

    rotation_matrix, _ = cv2.Rodrigues(rot_vec)

    intrinsic_matrix = np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0]
    ])

    extrinsic_matrix = np.eye(4)
    extrinsic_matrix[:3, :3] = rotation_matrix
    extrinsic_matrix[:3, 3] = tra_vec.reshape(3)

    return intrinsic_matrix, distortion, rot_vec, extrinsic_matrix


def calculate_calibration_errors(result: OptimizeResult,
                                 fix_cx_cy: bool = False,
                                 n_distortion_coefs: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    intrinsic_std, distortion_std, rot_vec_std, extrinsic_std = get_calibration(
        calculate_errors(result),
        image_size_xy=(0, 0),
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )
    return intrinsic_std, distortion_std, rot_vec_std, extrinsic_std[:3, 3]


def print_calibration(result: OptimizeResult,
                      image_size_xy: tuple = (2500, 2000),
                      fix_cx_cy: bool = False,
                      n_distortion_coefs: int = 5) -> None:

    intrinsic_matrix, distortion, rvec, extrinsic_matrix = get_calibration(
        result.x,
        image_size_xy=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )

    print()
    print("-" * 60)
    print("CALIBRATION RESULT")
    print("-" * 60)

    print()
    print("Intrinsic matrix:")

    print(intrinsic_matrix)

    print()
    print("Distortion coefficients:")
    print(distortion)

    print()
    print("Rotation vector:")
    print(rvec)

    print()
    print("Extrinsic matrix:")
    print(extrinsic_matrix)

    print()
    print("Optimization:")
    print("success:", result.success)
    print("message:", result.message)
    print("cost:", result.cost)
    print("fit values:")
    names = params_names(
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs
    )
    for each_err, each_value, each_name in zip(calculate_errors(result), result.x, names):
        print(f"{each_name:>6}: {each_value:>15.5f} +/- {each_err:0.5f}")


def calibrate_camera(robot_positions: np.ndarray,
                     image_center_points: np.ndarray,
                     radii: np.ndarray,
                     sigmas: np.ndarray,
                     focal_length_initial: float = 2000.0,
                     camera_distance_initial: float = 80.0,
                     image_size_xy: tuple[int, int] = (2500, 2000),
                     fix_cx_cy: bool = False,
                     n_distortion_coefs: int = 5) -> OptimizeResult:
    """
        Estimate camera intrinsics and extrinsics.

    :param robot_positions: positons of the center points (e.g., of a sphere hold by a robot) in space N*3
    :param image_center_points: positions of the center points on the images taken
    :param radii: radii of the sphere hold by a robot
    :param sigmas: bluring sigmas of the edges of the sphere hold by a robot
    :param focal_length_initial: initial focal length value
    :param camera_distance_initial: initial estimated distance of the focal plane to the camera
    :param image_size_xy: shape of the images taken
    :param fix_cx_cy: whether to fix the principal point (cx, cy) in the intrinsic matrix to be a half of image size
    :param n_distortion_coefs: number of distortion coefficients
    :return: optimized results from least_squares of scipy module
    """

    # estimate robot -> camera initial rotation
    r_initial = estimate_r_initial(robot_positions, image_center_points, radii, sigmas)

    robot_positions = np.asarray(robot_positions, dtype=np.float64)
    image_center_points = np.asarray(image_center_points, dtype=np.float64)

    if robot_positions.ndim != 2 or robot_positions.shape[1] != 3:
        raise ValueError(
            "robot_positions must have shape (N, 3)"
        )

    if image_center_points.ndim != 2 or image_center_points.shape[1] != 2:
        raise ValueError(
            "image_center_points must have shape (N, 2)"
        )

    if len(robot_positions) != len(image_center_points):
        raise ValueError(
            "robot_positions and image_center_points must have the same number of entries"
        )

    if len(robot_positions) < 10 + n_distortion_coefs:
        raise ValueError(
            f"At least {10 + n_distortion_coefs} measurements are recommended"
        )

    initial_params = make_initial_parameters(
        focal_length=focal_length_initial,
        camera_distance=camera_distance_initial,
        image_size=image_size_xy,
        fix_cx_cy=fix_cx_cy,
        n_distortion_coefs=n_distortion_coefs,
        r_initial=r_initial,
    )

    result = least_squares(
        residuals,
        initial_params,
        args=(
            robot_positions,
            image_center_points
        ),
        kwargs={
            "n_distortion_coefs": n_distortion_coefs,
            "image_size": image_size_xy,
            "fix_cx_cy": fix_cx_cy,
        },

        loss="soft_l1",
        x_scale="jac",
    )

    return result


def back_projected_point(robot_pos: np.ndarray,
                         intrinsic_matrix: np.ndarray,
                         extrinsic_matrix: np.ndarray,
                         distortion: np.ndarray) -> np.ndarray:
    """
        Back projecting 3D point to 2D image
    :param robot_pos: 3D points to project
    :param intrinsic_matrix: intrinsic matrix
    :param extrinsic_matrix: extrinsic matrix
    :param distortion:
    :return:
    """
    R = extrinsic_matrix[:3, :3]
    tvec = extrinsic_matrix[:3, 3]
    rvec = cv2.Rodrigues(R)[0].reshape(-1)
    return cv2.projectPoints(
        robot_pos,
        rvec,
        tvec,
        intrinsic_matrix,
        distortion
    )[0][:, 0]


def calculate_RMSE(result: OptimizeResult,
                   standardized: bool = True) -> float:
    res = result.fun
    mse = np.mean(res**2)
    rmse = np.sqrt(mse)
    if standardized:
        rmse /= len(res)

    return rmse
