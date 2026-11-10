# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Support functions"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import overload

import numpy as np
from scipy.optimize import OptimizeResult


#: Default significant digits kept from a one-sigma estimate.
ERROR_SIGNIFICANT_DIGITS = 2
#: Default ceiling on the significant digits of a reported value.
MAX_VALUE_SIGNIFICANT_DIGITS = 8
#: Default decimals of the nozzle home position (3 = 1 um).
NOZZLE_HOME_DECIMALS = 3


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
    """Estimate one-sigma parameter uncertainties from the fit Jacobian.

    The covariance is computed from the pseudoinverse of the Jacobian, so
    rank-deficient normal equations return finite values instead of raising
    ``LinAlgError``. When the fit has no residual degrees of freedom, or the
    residuals/Jacobian are not finite, the uncertainties are undefined and
    ``nan`` is returned.
    """
    residuals = np.asarray(result.fun, dtype=np.float64).reshape(-1)
    jacobian = np.asarray(result.jac, dtype=np.float64)

    if jacobian.ndim != 2 or jacobian.shape[0] != residuals.size:
        raise ValueError(
            "result.jac must be a 2D array with one row per residual"
        )

    n_residuals, n_params = jacobian.shape
    if n_params == 0:
        return np.empty(0, dtype=np.float64)
    if n_residuals <= n_params:
        return np.full(n_params, np.nan, dtype=np.float64)
    if not np.all(np.isfinite(residuals)) or not np.all(np.isfinite(jacobian)):
        return np.full(n_params, np.nan, dtype=np.float64)

    sigma2 = float(np.dot(residuals, residuals) / (n_residuals - n_params))
    if not np.isfinite(sigma2) or sigma2 < 0.0:
        return np.full(n_params, np.nan, dtype=np.float64)

    try:
        jacobian_pinv = np.linalg.pinv(jacobian)
    except np.linalg.LinAlgError:
        return np.full(n_params, np.nan, dtype=np.float64)

    covariance = sigma2 * (jacobian_pinv @ jacobian_pinv.T)
    variances = np.diag(covariance)
    # Round-off can make a numerically zero variance slightly negative.
    variances = np.where(variances >= 0.0, variances, np.nan)
    return np.sqrt(variances)


def _positive_zero(value: float) -> float:
    """Normalise ``-0.0`` to ``0.0`` so the serialized output has one zero."""
    return 0.0 if value == 0.0 else value


@dataclass(frozen=True)
class ReportPrecision:
    """How many digits a reported or stored result keeps.

    ``error_significant_digits`` is the number of significant digits kept from a
    one-sigma estimate; the matching value is rounded to the same decimal place.
    ``0`` disables the rounding and reports the full float precision.
    ``max_value_significant_digits`` caps the digits a value keeps, so a
    collapsed covariance cannot push meaningless digits into the result.
    ``nozzle_home_decimals`` fixes the decimals of the nozzle home position;
    ``None`` keeps full precision. ``round_stored_results`` decides whether the
    YAML/JSON artifacts follow the rule or keep full precision while only the
    console is rounded.
    """

    error_significant_digits: int = ERROR_SIGNIFICANT_DIGITS
    max_value_significant_digits: int = MAX_VALUE_SIGNIFICANT_DIGITS
    nozzle_home_decimals: int | None = NOZZLE_HOME_DECIMALS
    round_stored_results: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.error_significant_digits <= 15:
            raise ValueError(
                "error_significant_digits must be between 0 and 15, got "
                f"{self.error_significant_digits}"
            )
        if self.max_value_significant_digits < 1:
            raise ValueError(
                "max_value_significant_digits must be at least 1, got "
                f"{self.max_value_significant_digits}"
            )
        decimals = self.nozzle_home_decimals
        if decimals is not None and not 0 <= decimals <= 12:
            raise ValueError(
                "nozzle_home_decimals must be between 0 and 12 or None, got "
                f"{decimals}"
            )

    @property
    def rounds_values(self) -> bool:
        """Whether any reported value is rounded."""
        return self.error_significant_digits > 0

    def for_storage(self) -> ReportPrecision:
        """Return the precision to apply to a stored result document."""
        return self if self.round_stored_results else NO_ROUNDING

    def decimal_place(self, sigma: float) -> int | None:
        """Return the ``round`` decimal place implied by a one-sigma."""
        if not self.rounds_values:
            return None
        if not math.isfinite(sigma) or sigma <= 0.0:
            return None
        return (self.error_significant_digits - 1) - math.floor(math.log10(sigma))

    def value_place(self, value: float) -> int | None:
        """Return the ``round`` place that keeps the value's leading digits."""
        if not self.rounds_values or value == 0.0:
            return None
        return (self.max_value_significant_digits - 1) - math.floor(
            math.log10(abs(value))
        )

    @overload
    def reported(self, value: float, sigma: float) -> tuple[float, float]: ...

    @overload
    def reported(self, value: float, sigma: None) -> tuple[float, None]: ...

    def reported(self, value: float, sigma: float | None) -> tuple[float, float | None]:
        """Round a measurement and its one-sigma to the same decimal place.

        Values whose uncertainty is missing, ``nan``, or ``0`` are returned
        unchanged: they carry no uncertainty information, so rounding them would
        claim precision that was never estimated.
        """
        value = float(value)
        if sigma is None:
            return value, None

        sigma = float(sigma)
        place = self.decimal_place(sigma)
        if place is None or not math.isfinite(value):
            return value, sigma

        limit = self.value_place(value)
        value_place = place if limit is None else min(place, limit)
        return (
            _positive_zero(round(value, value_place)),
            _positive_zero(round(sigma, place)),
        )

    def reported_error(self, sigma: float) -> float:
        """Round a one-sigma that has no matching value in the report."""
        sigma = float(sigma)
        place = self.decimal_place(sigma)
        if place is None:
            return sigma
        return _positive_zero(round(sigma, place))


#: Precision used when no caller supplies an explicit :class:`ReportPrecision`.
DEFAULT_REPORT_PRECISION = ReportPrecision()
#: Precision that keeps every stored value at full float precision.
NO_ROUNDING = ReportPrecision(
    error_significant_digits=0,
    nozzle_home_decimals=None,
    round_stored_results=False,
)


@overload
def reported(value: float, sigma: float) -> tuple[float, float]: ...


@overload
def reported(value: float, sigma: None) -> tuple[float, None]: ...


def reported(value: float, sigma: float | None) -> tuple[float, float | None]:
    """Round a measurement and its one-sigma with the default precision.

    See :meth:`ReportPrecision.reported` for the rule. Callers that expose a
    configuration (the CLI and the Ice servant) should use their own
    :class:`ReportPrecision` instead of this module-level default.
    """
    return DEFAULT_REPORT_PRECISION.reported(value, sigma)


def reported_error(sigma: float) -> float:
    """Round a standalone one-sigma with the default precision."""
    return DEFAULT_REPORT_PRECISION.reported_error(sigma)


def format_number(value: float) -> str:
    """Render a float with the shortest exact round-trip representation."""
    return str(float(value))
