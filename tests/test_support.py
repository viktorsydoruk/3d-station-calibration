# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for shared numerical support helpers."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from station_calibration.support import (
    ERROR_SIGNIFICANT_DIGITS,
    MAX_VALUE_SIGNIFICANT_DIGITS,
    NOZZLE_HOME_DECIMALS,
    ReportPrecision,
    calculate_errors,
    find_proper_args_to_compare,
    fit_line_general_form,
    format_number,
    intersect_lines,
    reported,
    reported_error,
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


def test_reported_rounds_value_to_two_significant_error_digits() -> None:
    value, error = reported(14788.043071123456, 0.1234)

    assert value == pytest.approx(14788.04)
    assert error == pytest.approx(0.12)
    assert format_number(value).count(".") == 1


def test_reported_keeps_small_magnitudes_intact() -> None:
    value, error = reported(-1.23456789012e-05, 3.1e-08)

    assert value == pytest.approx(-1.2346e-05, rel=1e-3)
    assert error == pytest.approx(3.1e-08)


def test_reported_uses_the_same_place_for_value_and_error() -> None:
    value, error = reported(315.487391203948, 0.021)

    assert value == pytest.approx(315.487)
    # Two significant digits of 0.021 are 0.021, so the last value digit is
    # the third decimal.
    assert error == pytest.approx(0.021)
    assert round(value, 3) == value


@pytest.mark.parametrize("sigma", [None, 0.0, float("nan"), float("inf")])
def test_reported_leaves_values_without_a_usable_sigma_untouched(
    sigma: float | None,
) -> None:
    value, error = reported(1.2345678901234, sigma)

    assert value == 1.2345678901234
    if sigma is None:
        assert error is None
    elif np.isnan(sigma):
        assert np.isnan(error)
    else:
        assert error == sigma


def test_reported_leaves_non_finite_values_untouched() -> None:
    value, error = reported(float("nan"), 0.1)

    assert np.isnan(value)
    assert error == 0.1


def test_reported_normalises_negative_zero() -> None:
    value, error = reported(-3.0e-12, 1.0e-3)

    assert value == 0.0
    assert np.copysign(1.0, value) > 0.0
    assert error == pytest.approx(1.0e-3)


def test_reported_keeps_an_error_below_the_value_resolution() -> None:
    value, error = reported(1.0, 1.0e-9)

    assert value == 1.0
    assert error == pytest.approx(1.0e-9)


def test_reported_caps_the_value_at_eight_significant_digits() -> None:
    value, error = reported(1.2345678901234, 1.0e-12)

    assert value == pytest.approx(1.2345679)
    assert error == pytest.approx(1.0e-12)


def test_reported_significant_digit_limits() -> None:
    assert ERROR_SIGNIFICANT_DIGITS == 2
    assert MAX_VALUE_SIGNIFICANT_DIGITS == 8


def test_report_precision_defaults_match_the_module_constants() -> None:
    precision = ReportPrecision()

    assert precision.error_significant_digits == ERROR_SIGNIFICANT_DIGITS
    assert precision.max_value_significant_digits == MAX_VALUE_SIGNIFICANT_DIGITS
    assert precision.nozzle_home_decimals == NOZZLE_HOME_DECIMALS
    assert precision.round_stored_results is True


def test_report_precision_rounds_with_its_own_digit_count() -> None:
    precision = ReportPrecision(error_significant_digits=1)

    value, error = precision.reported(315.487391203948, 0.021)

    assert value == pytest.approx(315.49)
    assert error == pytest.approx(0.02)


def test_report_precision_zero_digits_keeps_full_precision() -> None:
    precision = ReportPrecision(error_significant_digits=0)

    assert precision.reported(315.487391203948, 0.021) == (
        315.487391203948,
        0.021,
    )
    assert precision.reported_error(0.0003141592653) == 0.0003141592653


def test_report_precision_for_storage_disables_every_rounding() -> None:
    precision = ReportPrecision()
    assert precision.for_storage() is precision

    storage = ReportPrecision(round_stored_results=False).for_storage()

    assert storage.rounds_values is False
    assert storage.nozzle_home_decimals is None
    assert storage.reported(315.487391203948, 0.021)[0] == 315.487391203948


@pytest.mark.parametrize(
    "kwargs",
    [
        {"error_significant_digits": -1},
        {"error_significant_digits": 16},
        {"max_value_significant_digits": 0},
        {"nozzle_home_decimals": -1},
        {"nozzle_home_decimals": 13},
    ],
)
def test_report_precision_rejects_out_of_range_values(kwargs) -> None:
    with pytest.raises(ValueError):
        ReportPrecision(**kwargs)


def test_reported_error_rounds_standalone_sigmas() -> None:
    assert reported_error(0.0003141592653) == pytest.approx(0.00031)
    assert reported_error(0.021) == pytest.approx(0.021)
    assert reported_error(0.0) == 0.0
    assert reported_error(-0.0) == 0.0
    assert np.isnan(reported_error(float("nan")))
    assert reported_error(float("inf")) == float("inf")


def test_format_number_renders_the_shortest_round_trip_value() -> None:
    assert format_number(1.0) == "1.0"
    assert format_number(315.487) == "315.487"
    assert format_number(1.0e-9) == "1e-09"
    assert format_number(np.float64(-0.0)) == "-0.0"


def test_format_number_matches_the_reported_value_text() -> None:
    value, error = reported(14788.043071123456, 0.1234)

    assert format_number(value) == "14788.04"
    assert format_number(error) == "0.12"
