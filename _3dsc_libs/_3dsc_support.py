"""Support functions"""

import numpy as np
from scipy.optimize._optimize import OptimizeResult


def find_proper_args_to_compare(robot_positions: np.ndarray,
                                sel_arg: int) -> tuple[int, int]:
    left_arg = [0, 1, 2]
    left_arg.remove(sel_arg)
    r_pos_0_min = np.min(np.unique(robot_positions[:, sel_arg]))
    r_pos_0_max = np.max(np.unique(robot_positions[:, sel_arg]))
    for each_r_pos_1 in np.unique(robot_positions[:, left_arg[0]]):
        for each_r_pos_2 in np.unique(robot_positions[:, left_arg[1]]):
            min_arg = np.argwhere((robot_positions[:, sel_arg] == r_pos_0_min)
                                  & (robot_positions[:, left_arg[0]] == each_r_pos_1)
                                  & (robot_positions[:, left_arg[1]] == each_r_pos_2)).flatten()
            max_arg = np.argwhere((robot_positions[:, sel_arg] == r_pos_0_max)
                                  & (robot_positions[:, left_arg[0]] == each_r_pos_1)
                                  & (robot_positions[:, left_arg[1]] == each_r_pos_2)).flatten()
            if len(min_arg) > 0 and len(max_arg) > 0:
                break
        if len(min_arg) > 0 and len(max_arg) > 0:
            break

    return min_arg[0], max_arg[0]


def fit_line_general_form(x, y):
    # x, y are 1D numpy arrays of equal length
    M = np.column_stack([x, y, np.ones_like(x)])

    # SVD: M = U * S * Vt
    _, _, Vt = np.linalg.svd(M)

    # The solution is the last row of Vt (smallest singular value)
    a, b, c = Vt[-1]

    # Optional: normalize (e.g., so that a^2 + b^2 = 1)
    norm = np.sqrt(a*a + b*b)
    a, b, c = a/norm, b/norm, c/norm

    return a, b, c


def intersect_lines(a1, b1, c1, a2, b2, c2):
    A = np.array([[a1, b1],
                  [a2, b2]], dtype=float)
    C = np.array([-c1, -c2], dtype=float)

    # Check for parallel lines
    if abs(np.linalg.det(A)) < 1e-12:
        # raise ValueError("Lines are parallel or identical")
        return None

    x, y = np.linalg.solve(A, C)
    return x, y


def calculate_errors(result: OptimizeResult) -> np.ndarray:
    res = result.fun
    m, n = result.jac.shape
    sigma2 =  np.sum(res**2) / (m - n)

    J: np.ndarray  =  result.jac
    JTJ_inv  =  np.linalg.inv(J.T @ J)
    cov = JTJ_inv * sigma2

    return np.sqrt(np.diag(cov))
