# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for numerical diagnostics and initial rotation handling."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from station_calibration import (
    back_projected_point,
    calculate_RMSE,
    calculate_calibration_errors,
    calculate_errors,
    check_distortion_monotonicity,
    print_calibration,
    radial_distortion_scale,
    radial_scale_profile,
)
import station_calibration.calibration.initialization as initialization_module
import station_calibration.calibration.metrics as metrics_module
from station_calibration.calibration.initialization import (
    _orthonormalize_rotation,
    estimate_r_initial,
    extract_z_lines,
    make_initial_parameters,
)


def _result(fun: list[float], jac: np.ndarray) -> OptimizeResult:
    return OptimizeResult(
        x=np.zeros(jac.shape[1]),
        fun=np.asarray(fun, dtype=np.float64),
        jac=np.asarray(jac, dtype=np.float64),
        success=True,
        cost=0.0,
        message="test",
    )


def _intrinsic(focal_length: float = 1000.0) -> np.ndarray:
    return _intrinsic_at(focal_length, focal_length, 500.0, 500.0)


def _intrinsic_at(
    focal_x: float,
    focal_y: float,
    center_x: float,
    center_y: float,
) -> np.ndarray:
    return np.array(
        [
            [focal_x, 0.0, center_x],
            [0.0, focal_y, center_y],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def test_calculate_errors_matches_classical_covariance() -> None:
    rng = np.random.default_rng(0)
    jacobian = rng.normal(size=(20, 5))
    residuals = rng.normal(size=20)
    result = _result(residuals, jacobian)

    sigma2 = np.sum(residuals ** 2) / (len(residuals) - jacobian.shape[1])
    expected = np.sqrt(np.diag(np.linalg.inv(jacobian.T @ jacobian) * sigma2))

    np.testing.assert_allclose(
        calculate_errors(result), expected, rtol=1e-9, atol=1e-12
    )


def test_calculate_errors_handles_rank_deficient_jacobian() -> None:
    jacobian = np.array(
        [
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
        ]
    )
    result = _result([1.0, -1.0, 1.0, -1.0], jacobian)

    errors = calculate_errors(result)

    assert errors.shape == (2,)
    assert np.all(np.isfinite(errors))


def test_calculate_errors_returns_nan_without_degrees_of_freedom() -> None:
    result = _result([1.0, 2.0], np.eye(2))

    errors = calculate_errors(result)

    assert np.all(np.isnan(errors))


def test_calculate_errors_rejects_mismatched_jacobian() -> None:
    with pytest.raises(ValueError, match="one row per residual"):
        calculate_errors(_result([1.0, 2.0], np.eye(3)))


def test_calculate_calibration_errors_maps_free_principal_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    errors = np.arange(15, dtype=np.float64)
    monkeypatch.setattr(metrics_module, "calculate_errors", lambda result: errors)

    intrinsic_std, distortion_std, rot_vec_std, tra_vec_std = (
        calculate_calibration_errors(
            None,  # type: ignore[arg-type]
            fix_cx_cy=False,
            n_distortion_coefs=5,
        )
    )

    np.testing.assert_allclose(
        intrinsic_std,
        [[0.0, 0.0, 2.0], [0.0, 1.0, 3.0], [0.0, 0.0, 0.0]],
    )
    np.testing.assert_allclose(distortion_std[:5], [4.0, 5.0, 6.0, 7.0, 8.0])
    np.testing.assert_allclose(distortion_std[5:], 0.0)
    np.testing.assert_allclose(rot_vec_std, [9.0, 10.0, 11.0])
    np.testing.assert_allclose(tra_vec_std, [12.0, 13.0, 14.0])


def test_calculate_calibration_errors_maps_fixed_principal_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    errors = np.arange(12, dtype=np.float64)
    monkeypatch.setattr(metrics_module, "calculate_errors", lambda result: errors)

    intrinsic_std, distortion_std, rot_vec_std, tra_vec_std = (
        calculate_calibration_errors(
            None,  # type: ignore[arg-type]
            fix_cx_cy=True,
            n_distortion_coefs=4,
        )
    )

    np.testing.assert_allclose(
        intrinsic_std,
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
    )
    np.testing.assert_allclose(distortion_std[:4], [2.0, 3.0, 4.0, 5.0])
    np.testing.assert_allclose(distortion_std[4:], 0.0)
    np.testing.assert_allclose(rot_vec_std, [6.0, 7.0, 8.0])
    np.testing.assert_allclose(tra_vec_std, [9.0, 10.0, 11.0])


def test_calculate_RMSE_plain_and_standardized() -> None:
    result = _result([3.0, 4.0], np.ones((2, 1)))

    assert calculate_RMSE(result, standardized=False) == pytest.approx(
        np.sqrt(12.5)
    )
    assert calculate_RMSE(result, standardized=True) == pytest.approx(5.0)
    assert calculate_RMSE(result) == pytest.approx(5.0)


def test_calculate_RMSE_standardized_is_nan_without_degrees_of_freedom() -> None:
    result = _result([3.0, 4.0], np.eye(2))

    assert np.isnan(calculate_RMSE(result, standardized=True))
    assert calculate_RMSE(result, standardized=False) == pytest.approx(
        np.sqrt(12.5)
    )


def test_calculate_RMSE_returns_nan_for_nonfinite_residuals() -> None:
    result = _result([1.0, np.nan], np.ones((2, 1)))

    assert np.isnan(calculate_RMSE(result, standardized=False))
    assert np.isnan(calculate_RMSE(result, standardized=True))


def test_calculate_RMSE_prefers_unweighted_residuals() -> None:
    result = _result([10.0, 10.0], np.ones((2, 1)))
    result.raw_fun = np.array([3.0, 4.0])

    assert calculate_RMSE(result, standardized=False) == pytest.approx(
        np.sqrt(12.5)
    )
    assert calculate_RMSE(result, standardized=True) == pytest.approx(5.0)


def test_distortion_monotonicity_accepts_identity_and_decreasing_models() -> None:
    intrinsic = _intrinsic()

    assert check_distortion_monotonicity(np.zeros(14), intrinsic, (1000, 1000))

    decreasing = np.zeros(14)
    decreasing[0] = -0.5
    assert check_distortion_monotonicity(decreasing, intrinsic, (1000, 1000))


@pytest.mark.parametrize("coefficient_index", [5, 6, 7])
def test_distortion_monotonicity_checks_higher_radial_terms(
    coefficient_index: int,
) -> None:
    distortion = np.zeros(14)
    distortion[0] = 1.0
    distortion[coefficient_index] = -100.0

    assert not check_distortion_monotonicity(
        distortion, _intrinsic(), (1000, 1000)
    )


def test_distortion_monotonicity_rejects_negative_radial_scale() -> None:
    distortion = np.zeros(14)
    distortion[0] = -100.0

    assert not check_distortion_monotonicity(
        distortion, _intrinsic(), (1000, 1000)
    )


def test_distortion_monotonicity_rejects_folding_numerator_mapping() -> None:
    distortion = np.zeros(14)
    distortion[0] = -1.2
    intrinsic = _intrinsic_at(2000.0, 2000.0, 1250.0, 1000.0)

    # The scale stays positive, but r * scale is already decreasing at the
    # image corner.
    assert not check_distortion_monotonicity(
        distortion, intrinsic, (2500, 2000)
    )


def test_distortion_monotonicity_rejects_folding_denominator_mapping() -> None:
    distortion = np.zeros(14)
    distortion[5] = 2.0
    intrinsic = _intrinsic_at(2000.0, 2000.0, 1250.0, 1000.0)

    # k4 belongs to the rational denominator, not to the numerator polynomial.
    assert not check_distortion_monotonicity(
        distortion, intrinsic, (2500, 2000)
    )


def test_distortion_monotonicity_uses_all_image_corners() -> None:
    distortion = np.zeros(14)
    distortion[0] = -0.5
    intrinsic = _intrinsic_at(1000.0, 1000.0, 0.0, 0.0)

    # The old centered estimate used hypot(width/2, height/2) / fx, which
    # missed the fold near the far corner for this off-centre principal point.
    assert not check_distortion_monotonicity(
        distortion, intrinsic, (1000, 1000)
    )


def test_distortion_monotonicity_accepts_mild_radial_models() -> None:
    distortion = np.zeros(14)
    distortion[0] = -0.1
    intrinsic = _intrinsic_at(2000.0, 2000.0, 1250.0, 1000.0)

    assert check_distortion_monotonicity(
        distortion, intrinsic, (2500, 2000)
    )


def test_distortion_monotonicity_rejects_invalid_inputs() -> None:
    distortion = np.zeros(14)
    distortion[0] = np.nan

    assert not check_distortion_monotonicity(
        distortion, _intrinsic(), (1000, 1000)
    )
    assert not check_distortion_monotonicity(
        np.zeros(14), _intrinsic(focal_length=0.0), (1000, 1000)
    )
    assert not check_distortion_monotonicity(
        np.zeros(14), _intrinsic(), (-1, 1000)
    )


def test_radial_distortion_scale_is_one_for_a_pinhole_model() -> None:
    radii = np.array([0.0, 0.05, 0.1])

    np.testing.assert_allclose(
        radial_distortion_scale(np.zeros(14), radii), 1.0
    )


def test_radial_distortion_scale_matches_the_polynomial_terms() -> None:
    distortion = np.zeros(14)
    distortion[0] = -0.1
    distortion[1] = 0.02
    radii = np.array([0.1, 0.2])

    expected = 1.0 + distortion[0] * radii ** 2 + distortion[1] * radii ** 4

    np.testing.assert_allclose(
        radial_distortion_scale(distortion, radii), expected
    )


def test_radial_distortion_scale_matches_the_rational_denominator() -> None:
    distortion = np.zeros(14)
    distortion[5] = 0.5  # k4
    radii = np.array([0.2])

    expected = 1.0 / (1.0 + 0.5 * 0.2 ** 2)

    np.testing.assert_allclose(
        radial_distortion_scale(distortion, radii), expected
    )


def test_radial_distortion_scale_validates_inputs() -> None:
    with pytest.raises(ValueError, match="one-dimensional"):
        radial_distortion_scale(np.zeros(14), np.zeros((2, 2)))
    with pytest.raises(ValueError, match="finite"):
        radial_distortion_scale(np.zeros(14), np.array([0.0, np.nan]))
    with pytest.raises(ValueError, match="non-negative"):
        radial_distortion_scale(np.zeros(14), np.array([-0.1]))
    with pytest.raises(ValueError, match="distortion"):
        radial_distortion_scale(np.array([np.nan]), np.array([0.1]))


def test_radial_scale_profile_samples_the_observed_radii() -> None:
    intrinsic = _intrinsic()
    centers = np.array(
        [[500.0, 500.0], [600.0, 500.0], [700.0, 500.0]],
        dtype=np.float64,
    )

    profile = radial_scale_profile(
        centers, intrinsic, np.zeros(14), quantiles=(0.0, 0.5, 1.0)
    )

    assert profile is not None
    np.testing.assert_allclose(profile["radii"], [0.0, 0.1, 0.2])
    np.testing.assert_allclose(profile["scale"], [1.0, 1.0, 1.0])

    empty_distortion = radial_scale_profile(
        centers, intrinsic, np.array([]), quantiles=(0.0, 0.5, 1.0)
    )

    assert empty_distortion is not None
    np.testing.assert_allclose(empty_distortion["scale"], [1.0, 1.0, 1.0])


def test_radial_scale_profile_undistorts_before_sampling() -> None:
    intrinsic = _intrinsic()
    distortion = np.zeros(14)
    distortion[0] = -0.1
    ideal = np.array([[0.1, 0.05]])

    projected, _ = cv2.projectPoints(
        np.column_stack([ideal, np.ones(1)]),
        np.zeros(3),
        np.zeros(3),
        intrinsic,
        distortion,
    )
    profile = radial_scale_profile(
        projected.reshape(-1, 2),
        intrinsic,
        distortion,
        quantiles=(1.0,),
    )

    assert profile is not None
    ideal_radius = float(np.linalg.norm(ideal))
    np.testing.assert_allclose(profile["radii"], [ideal_radius], rtol=1e-6)
    np.testing.assert_allclose(
        profile["scale"],
        [1.0 + distortion[0] * ideal_radius ** 2],
        rtol=1e-6,
    )


def test_radial_scale_profile_returns_none_without_usable_points() -> None:
    assert radial_scale_profile(np.empty((0, 2)), _intrinsic(), np.zeros(14)) is None
    assert radial_scale_profile(np.zeros((2, 2)), np.eye(2), np.zeros(14)) is None
    assert radial_scale_profile(
        np.full((2, 2), np.nan), _intrinsic(), np.zeros(14)
    ) is None


def test_radial_scale_profile_validates_quantiles() -> None:
    with pytest.raises(ValueError, match="quantiles"):
        radial_scale_profile(
            np.zeros((1, 2)),
            _intrinsic(),
            np.zeros(14),
            quantiles=(0.0, 1.5),
        )


def _assert_proper_rotation(matrix: np.ndarray) -> None:
    np.testing.assert_allclose(matrix.T @ matrix, np.eye(3), atol=1e-12)
    assert np.linalg.det(matrix) == pytest.approx(1.0, abs=1e-12)


def test_estimate_r_initial_returns_proper_rotation() -> None:
    rng = np.random.default_rng(1)
    n_points = 30
    robot_positions = rng.normal(size=(n_points, 3))
    image_center_points = rng.normal(size=(n_points, 2)) * 100.0 + 500.0
    radii = rng.uniform(10.0, 15.0, n_points)
    sigmas = rng.uniform(0.5, 2.0, n_points)

    rotation = estimate_r_initial(
        robot_positions, image_center_points, radii, sigmas
    )

    _assert_proper_rotation(rotation)


def test_estimate_r_initial_falls_back_for_degenerate_data() -> None:
    rotation = estimate_r_initial(
        np.ones((5, 3)),
        np.ones((5, 2)),
        np.ones(5),
        np.ones(5),
    )

    np.testing.assert_allclose(rotation, np.eye(3))


def test_make_initial_parameters_orthonormalizes_rotation() -> None:
    params = make_initial_parameters(
        focal_length=1000.0,
        camera_distance=80.0,
        image_size=(1000, 1000),
        fix_cx_cy=True,
        n_distortion_coefs=0,
        r_initial=np.diag([1.0, 2.0, 1.0]),
    )

    rotation, _ = cv2.Rodrigues(params[2:5])

    _assert_proper_rotation(rotation)


def test_make_initial_parameters_keeps_free_principal_point() -> None:
    params = make_initial_parameters(
        focal_length=1000.0,
        camera_distance=80.0,
        image_size=(1000, 800),
        fix_cx_cy=False,
        n_distortion_coefs=5,
        r_initial=np.eye(3),
    )

    assert len(params) == 15
    np.testing.assert_allclose(params[:4], [1000.0, 1000.0, 500.0, 400.0])
    np.testing.assert_allclose(params[4:9], 0.0)


def test_distortion_monotonicity_accepts_empty_and_short_vectors() -> None:
    assert check_distortion_monotonicity(
        np.array([]), _intrinsic(), (1000, 1000)
    )
    assert check_distortion_monotonicity(
        np.array([0.0]), _intrinsic(), (1000, 1000)
    )


def test_distortion_monotonicity_rejects_bad_intrinsic_and_image_size() -> None:
    assert not check_distortion_monotonicity(
        np.zeros(14), np.eye(2), (1000, 1000)
    )
    assert not check_distortion_monotonicity(
        np.zeros(14), _intrinsic(), (float("inf"), 1000)
    )


def test_calculate_RMSE_handles_empty_and_mismatched_residuals() -> None:
    empty = OptimizeResult(
        fun=np.array([]),
        jac=np.empty((0, 0), dtype=np.float64),
    )
    assert np.isnan(calculate_RMSE(empty, standardized=False))

    mismatched = OptimizeResult(
        fun=np.array([1.0, 2.0]),
        jac=np.ones((3, 1), dtype=np.float64),
    )
    with pytest.raises(ValueError, match="one row per residual"):
        calculate_RMSE(mismatched)


def test_print_calibration_reports_parameter_uncertainties(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    params = make_initial_parameters(
        focal_length=1000.0,
        camera_distance=80.0,
        image_size=(1000, 800),
        fix_cx_cy=True,
        n_distortion_coefs=0,
        r_initial=np.eye(3),
    )
    result = OptimizeResult(
        x=params,
        fun=np.zeros(4),
        jac=np.ones((4, len(params))),
        success=True,
        message="ok",
        cost=0.0,
    )
    monkeypatch.setattr(
        metrics_module,
        "calculate_errors",
        lambda result: np.zeros(len(result.x)),
    )

    print_calibration(
        result,
        image_size_xy=(1000, 800),
        fix_cx_cy=True,
        n_distortion_coefs=0,
    )

    output = capsys.readouterr().out
    assert "CALIBRATION RESULT" in output
    assert "fx" in output
    assert "t3" in output


def test_print_calibration_rounds_to_two_error_digits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    params = make_initial_parameters(
        focal_length=1000.0,
        camera_distance=80.0,
        image_size=(1000, 800),
        fix_cx_cy=True,
        n_distortion_coefs=0,
        r_initial=np.eye(3),
    )
    result = OptimizeResult(
        x=params,
        fun=np.zeros(4),
        jac=np.ones((4, len(params))),
        success=True,
        message="ok",
        cost=0.0,
    )
    monkeypatch.setattr(
        metrics_module,
        "calculate_errors",
        lambda result: np.full(len(result.x), 0.01234),
    )

    print_calibration(
        result,
        image_size_xy=(1000, 800),
        fix_cx_cy=True,
        n_distortion_coefs=0,
    )

    output = capsys.readouterr().out
    assert output.count("+/- 0.012") == len(params)
    assert "1000.0 +/- 0.012" in output


def test_back_projected_point_projects_to_principal_point() -> None:
    intrinsic = _intrinsic()
    extrinsic = np.eye(4)
    extrinsic[2, 3] = 80.0

    point = back_projected_point(
        np.array([[0.0, 0.0, 0.0]]),
        intrinsic,
        extrinsic,
        np.zeros(5),
    )

    np.testing.assert_allclose(point, [[500.0, 500.0]], atol=1e-9)


def test_orthonormalize_rotation_handles_invalid_inputs_and_reflections() -> None:
    np.testing.assert_allclose(
        _orthonormalize_rotation(np.zeros((2, 2))),
        np.eye(3),
    )
    np.testing.assert_allclose(
        _orthonormalize_rotation(
            np.array(
                [
                    [np.nan, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ]
            )
        ),
        np.eye(3),
    )

    rotation = _orthonormalize_rotation(np.diag([-1.0, 1.0, 1.0]))

    _assert_proper_rotation(rotation)


def test_orthonormalize_rotation_falls_back_when_svd_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_svd(matrix):
        raise np.linalg.LinAlgError("singular")

    monkeypatch.setattr(initialization_module.np.linalg, "svd", fail_svd)

    np.testing.assert_allclose(
        _orthonormalize_rotation(np.eye(3)),
        np.eye(3),
    )


def test_extract_z_lines_intersects_image_lines() -> None:
    z = np.array([0.0, 10.0, 20.0, 30.0])
    robot_positions = np.vstack(
        [
            np.column_stack([np.zeros_like(z), np.zeros_like(z), z]),
            np.column_stack([np.full_like(z, 10.0), np.full_like(z, 10.0), z]),
        ]
    )
    image_center_points = np.vstack(
        [
            np.column_stack([100.0 + z, 200.0 + 2.0 * z]),
            np.column_stack([1000.0 - z, 200.0 + 3.0 * z]),
        ]
    )

    intersection = extract_z_lines(
        robot_positions,
        image_center_points,
        np.eye(3),
    )

    np.testing.assert_allclose(intersection, [640.0, 1280.0], atol=1e-6)
