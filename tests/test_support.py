# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for shared numerical support helpers."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from station_calibration.support import (
    calculate_errors,
    find_proper_args_to_compare,
    fit_line_general_form,
    intersect_lines,
)


def test_find_proper_args_to_compare_returns_matching_grid_pair() -> None:
    robot_positions = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 10.0],
            [5.0, 5.0, 0.0],
            [5.0, 5.0, 10.0],
            [10.0, 0.0, 0.0],
            [10.0, 0.0, 10.0],
        ]
    )

    first, last = find_proper_args_to_compare(robot_positions, sel_arg=2)

    assert (first, last) == (0, 1)


def test_fit_line_general_form_fits_a_collinear_set() -> None:
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = 2.0 * x + 3.0

    a, b, c = fit_line_general_form(x, y)

    np.testing.assert_allclose(a * x + b * y + c, 0.0, atol=1e-10)
    np.testing.assert_allclose(a * a + b * b, 1.0)


def test_intersect_lines_returns_intersection_and_none_for_parallel() -> None:
    assert intersect_lines(1.0, 0.0, -1.0, 0.0, 1.0, -2.0) == pytest.approx(
        (1.0, 2.0)
    )
    assert intersect_lines(1.0, 0.0, -1.0, 1.0, 0.0, -2.0) is None


def test_calculate_errors_handles_empty_parameter_vector() -> None:
    result = OptimizeResult(
        fun=np.array([1.0, 2.0]),
        jac=np.empty((2, 0), dtype=np.float64),
    )

    errors = calculate_errors(result)

    assert errors.shape == (0,)


def test_calculate_errors_returns_nan_for_nonfinite_inputs() -> None:
    result = OptimizeResult(
        fun=np.array([1.0, np.nan]),
        jac=np.ones((2, 1), dtype=np.float64),
    )

    assert np.all(np.isnan(calculate_errors(result)))


def test_calculate_errors_returns_nan_when_pseudoinverse_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_pinv(*args, **kwargs):
        raise np.linalg.LinAlgError("singular")

    monkeypatch.setattr(np.linalg, "pinv", fail_pinv)
    result = OptimizeResult(
        fun=np.array([1.0, 2.0, 3.0]),
        jac=np.ones((3, 1), dtype=np.float64),
    )

    assert np.all(np.isnan(calculate_errors(result)))


def test_calculate_errors_returns_nan_for_overflowing_residuals() -> None:
    result = OptimizeResult(
        fun=np.array([1e308, 1e308]),
        jac=np.ones((2, 1), dtype=np.float64),
    )

    with np.errstate(over="ignore"):
        assert np.all(np.isnan(calculate_errors(result)))
