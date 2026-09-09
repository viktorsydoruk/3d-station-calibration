import numpy as np
import cv2
import os
import glob

from scipy.optimize import least_squares
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

IMAGE_WIDTH = 2500
IMAGE_HEIGHT = 2000

CX_INITIAL = IMAGE_WIDTH / 2.0
CY_INITIAL = IMAGE_HEIGHT / 2.0


# ============================================================
# Robot -> camera initial rotation
#
# Robot:
#   +X = toward camera
#   +Y = right in image
#   +Z = up in image
#
# OpenCV camera:
#   +X = right
#   +Y = down
#   +Z = away from camera
#
# Therefore:
#
#   Xc =  Yr
#   Yc =  Zr
#   Zc = -Xr
# ============================================================

R_INITIAL = np.array([
    [0.0, 1.0, 0.0],
    [0.0, 0.0, -1.0],
    [-1.0, 0.0, 0.0]
], dtype=np.float64)

RVECS_INITIAL, _ = cv2.Rodrigues(R_INITIAL)


# ============================================================
# Parameter vector
#
# [0:4]   fx fy cx cy
# [4:9]   k1 k2 p1 p2 k3
# [9:12]  rotation vector
# [12:15] translation
# ============================================================

def make_initial_parameters(
    focal_length=2000.0,
    camera_distance=80.0
):
    """
    Create initial parameter vector.

    camera_distance is only used as an approximate initial
    translation. It may need adjustment depending on the
    robot coordinate origin.
    """

    params = np.zeros(15, dtype=np.float64)

    # Intrinsics
    params[0] = focal_length       # fx
    params[1] = focal_length       # fy
    params[2] = CX_INITIAL         # cx
    params[3] = CY_INITIAL         # cy

    # Distortion initially zero
    params[4:9] = 0.0

    # Initial rotation
    params[9:12] = RVECS_INITIAL.ravel()

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # This translation is only an initial guess.
    #
    # It assumes approximately that the robot origin is
    # around camera distance.
    #
    # We will improve this below if possible.
    # --------------------------------------------------------

    params[12] = 0.0
    params[13] = 0.0
    params[14] = camera_distance

    return params


# ============================================================
# Projection
# ============================================================

def project_points(params, robot_points):
    """
    Transform robot coordinates to camera coordinates and
    project them into the image.
    """

    fx, fy, cx, cy = params[0:4]

    k1, k2, p1, p2, k3 = params[4:9]

    rvec = params[9:12]
    tvec = params[12:15]

    camera_matrix = np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0]
    ])

    distortion = np.array([
        k1,
        k2,
        p1,
        p2,
        k3
    ])

    projected, _ = cv2.projectPoints(
        robot_points,
        rvec,
        tvec,
        camera_matrix,
        distortion
    )

    return projected.reshape(-1, 2)


# ============================================================
# Residual
# ============================================================

def residuals(
    params,
    robot_points,
    measured_image_points
):
    """
    Return x/y reprojection error for all measurements.
    """

    predicted = project_points(
        params,
        robot_points
    )

    error = predicted - measured_image_points

    return error.ravel()


# ============================================================
# Calibration
# ============================================================

def calibrate_camera(
    robot_points,
    image_points,
    focal_length_initial=2000.0,
    camera_distance_initial=80.0
):
    """
    Estimate camera intrinsics and robot -> camera extrinsics.
    """

    robot_points = np.asarray(robot_points, dtype=np.float64)

    image_points = np.asarray(image_points, dtype=np.float64)

    if robot_points.ndim != 2 or robot_points.shape[1] != 3:
        raise ValueError(
            "robot_points must have shape (N, 3)"
        )

    if image_points.ndim != 2 or image_points.shape[1] != 2:
        raise ValueError(
            "image_points must have shape (N, 2)"
        )

    if len(robot_points) != len(image_points):
        raise ValueError(
            "robot_points and image_points must have "
            "the same number of entries"
        )

    if len(robot_points) < 10:
        raise ValueError(
            "At least 10 measurements are recommended"
        )

    initial_params = make_initial_parameters(
        focal_length=focal_length_initial,
        camera_distance=camera_distance_initial
    )

    print("Initial parameters:")
    print(initial_params)

    result = least_squares(
        residuals,
        initial_params,
        args=(
            robot_points,
            image_points
        ),

        # Very useful because Hough detection can produce
        # occasional bad measurements.
        loss="soft_l1",

        # Start conservatively.
        x_scale="jac",

        verbose=1
    )

    return result


# ============================================================
# Results
# ============================================================

def print_calibration(result):

    params = result.x

    fx, fy, cx, cy = params[0:4]

    distortion = params[4:9]

    rvec = params[9:12]
    tvec = params[12:15]

    R, _ = cv2.Rodrigues(rvec)

    print()
    print("=" * 60)
    print("CALIBRATION RESULT")
    print("=" * 60)

    print()
    print("Camera matrix:")
    print()

    camera_matrix = np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0]
    ])

    print(camera_matrix)

    print()
    print("Distortion coefficients:")
    print(distortion)

    print()
    print("Rotation vector:")
    print(rvec)

    print()
    print("Rotation matrix:")
    print(R)

    print()
    print("Translation:")
    print(tvec)

    print()
    print("Optimization:")
    print("success:", result.success)
    print("message:", result.message)
    print("cost:", result.cost)

    return camera_matrix, distortion, R, tvec


# ============================================================
# Error analysis
# ============================================================

def calculate_errors(
    result,
    robot_points,
    image_points
):
    """
    Calculate individual reprojection errors.
    """

    predicted = project_points(
        result.x,
        robot_points
    )

    error_vectors = predicted - image_points

    error_distances = np.linalg.norm(
        error_vectors,
        axis=1
    )

    rms = np.sqrt(
        np.mean(error_distances ** 2)
    )

    mean = np.mean(error_distances)

    maximum = np.max(error_distances)

    print()
    print("=" * 60)
    print("REPROJECTION ERROR")
    print("=" * 60)

    print(f"Mean error : {mean:.4f} px")
    print(f"RMS error  : {rms:.4f} px")
    print(f"Max error  : {maximum:.4f} px")

    return predicted, error_vectors, error_distances

def load_robot_points(file: Path) -> np.ndarray:
    robot_points = np.loadtxt(
        file,
        delimiter=";",
        dtype=float
    )
    return robot_points

def get_image_points(image_folder: Path):
    image_points = []
    failed_images = []

    images = [file for file in image_folder.glob('*.tif')]
    print(len(images), "images are found")
    temp_folder = image_folder.joinpath('temp')
    temp_folder.mkdir(exist_ok=True)

    for i, image_path in enumerate(images):
        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        image_color = cv2.cvtColor(image,cv2.COLOR_BAYER_BG2BGR)
        # cv2.imwrite(temp_folder / 'convertedcolor.tif', image_color)
        image_gray = cv2.cvtColor(image, cv2.COLOR_BAYER_BG2GRAY)
        # cv2.imwrite(temp_folder / 'convertedgrey.tif', image_gray)

        #now get the center points
        # Detect circles
        circles = cv2.HoughCircles(
            image_gray,
            cv2.HOUGH_GRADIENT,
            dp=1.0,
            minDist=20,
            param1=60,
            param2=30,
            minRadius=30,
            maxRadius=400
        )
        result = image_color.copy()
        if circles is not None:
            circles = np.round(circles[0]).astype(int)

            # Take the first detected circle
            x, y, radius = circles[0]

            print(f"Ball center: ({x}, {y}) r={radius}")

            # Draw result
            cv2.circle(result, (x, y), radius, (0, 255, 0), 2)
            cv2.circle(result, (x, y), 3, (0, 0, 255), -1)

            cv2.imwrite(temp_folder / f"result{i:>04d}.png", result)
            image_points.append([float(x), float(y)])
        else:
            print(f"No circle found {i}")
            failed_images.append(i)
            cv2.imwrite(temp_folder / f"result{i:>04d}.png", result)
    return np.array(image_points), failed_images

if __name__ == "__main__":
    # folder with images and coordinates
    # main_folder = Path(r"D:/_seed_volume_carving/3Dcalibration/3D_20260821_2mm")
    main_folder = Path(r"P:/3Dcalibration/3D_20260824_2,3mm")

    # read robot coordinates
    robot_points = load_robot_points(main_folder / "Calibarion3DPositions.csv")
    robot_points = robot_points - robot_points[62] # substract the starting point
    print(len(robot_points), "robot coordinates are collected")

    image_points, failed_images = get_image_points(main_folder)
    print(len(image_points), " image points are collected; ", len(failed_images), " failed images")

    # delete failed images indizes from robot coordinates
    robot_points = np.delete(robot_points, failed_images, axis=0)

    print("left: ", f"images: {len(image_points)} and robot_points: {len(robot_points)}")

    result = calibrate_camera(
        robot_points,
        image_points,
        focal_length_initial=2000.0,
        camera_distance_initial=80.0
    )

    camera_matrix, distortion, R, t = print_calibration(result)

    predicted, errors, distances = calculate_errors(
        result,
        robot_points,
        image_points
    )