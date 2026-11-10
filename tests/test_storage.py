# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for point-cache storage."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

import station_calibration.storage.points as points_module
from station_calibration.storage import (
    NOZZLE_UNCERTAINTY_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    calibration_document,
    load_all_points,
    load_all_points_with_covariances,
    load_robot_positions,
    search_images,
    store_all_points,
    store_nozzle_uncertainty,
)


def test_point_cache_round_trip_preserves_float64(tmp_path: Path) -> None:
    robot_positions = np.array(
        [
            [312.1234567890123, -110.9876543210987, -36.4],
            [318.06, -107.94, -35.44],
        ],
        dtype=np.float64,
    )
    center_points = np.array(
        [
            [331.7058188960392, 629.0855863442323],
            [2045.384785120838, 915.3024372938667],
        ],
        dtype=np.float64,
    )
    radii = np.array([156.41471540876242, 170.65923626094033], dtype=np.float64)
    sigmas = np.array([6.58892138764756, 16.852260747805076], dtype=np.float64)
    image_sizes = np.array([[2048.0, 2448.0], [2048.0, 2448.0]], dtype=np.float64)
    directions = np.array([-1, 1], dtype=np.int8)

    point_file = tmp_path / "all_points.dat"
    store_all_points(
        point_file,
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_sizes,
        directions,
    )

    loaded = load_all_points(point_file)

    for array in loaded[:5]:
        assert array.dtype == np.float64
    assert loaded[5].dtype == np.int8

    np.testing.assert_array_equal(loaded[0], robot_positions)
    np.testing.assert_array_equal(loaded[1], center_points)
    np.testing.assert_array_equal(loaded[2], radii)
    np.testing.assert_array_equal(loaded[3], sigmas)
    np.testing.assert_array_equal(loaded[4], image_sizes)
    np.testing.assert_array_equal(loaded[5], directions)


def test_point_cache_round_trip_preserves_center_covariances(tmp_path: Path) -> None:
    robot_positions = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    center_points = np.array([[10.0, 20.0], [30.0, 40.0]])
    radii = np.array([100.0, 101.0])
    sigmas = np.array([2.0, 3.0])
    image_sizes = np.array([[2000.0, 3000.0], [2000.0, 3000.0]])
    directions = np.array([1, -1], dtype=np.int8)
    covariances = np.array(
        [
            [[0.01, 0.002], [0.002, 0.02]],
            [[0.03, -0.001], [-0.001, 0.04]],
        ]
    )

    point_file = tmp_path / "all_points.dat"
    store_all_points(
        point_file,
        robot_positions,
        center_points,
        radii,
        sigmas,
        image_sizes,
        directions,
        covariances,
    )

    loaded = load_all_points_with_covariances(point_file)

    np.testing.assert_array_equal(loaded[0], robot_positions)
    np.testing.assert_array_equal(loaded[1], center_points)
    np.testing.assert_array_equal(loaded[2], radii)
    np.testing.assert_array_equal(loaded[3], sigmas)
    np.testing.assert_array_equal(loaded[4], image_sizes)
    np.testing.assert_array_equal(loaded[5], directions)
    np.testing.assert_allclose(loaded[6], covariances, atol=1e-15)


def test_load_all_points_with_covariances_accepts_legacy_cache(
    tmp_path: Path,
) -> None:
    point_file = tmp_path / "legacy.dat"
    point_file.write_text(
        "Xr\tYr\tZr\tXc\tYc\tradius\tsigma border\t"
        "image height\timage width\tnozzle_direction\n"
        "1\t2\t3\t10\t20\t100\t2\t2000\t3000\t1\n",
        encoding="utf-8",
    )

    loaded = load_all_points_with_covariances(point_file)

    assert loaded[0].shape == (1, 3)
    assert loaded[6].shape == (1, 2, 2)
    assert np.all(np.isnan(loaded[6]))


def test_point_cache_failure_leaves_existing_file_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    point_file = tmp_path / "all_points.dat"
    point_file.write_text("original\n", encoding="utf-8")

    class FailingWriter:
        def writerow(self, row):
            return None

        def writerows(self, rows):
            raise RuntimeError("serialization failed")

    monkeypatch.setattr(
        points_module.csv,
        "writer",
        lambda *args, **kwargs: FailingWriter(),
    )

    with pytest.raises(RuntimeError, match="serialization failed"):
        store_all_points(
            point_file,
            np.zeros((1, 3)),
            np.zeros((1, 2)),
            np.zeros(1),
            np.zeros(1),
            np.zeros((1, 2)),
            np.zeros(1, dtype=np.int8),
        )

    assert point_file.read_text(encoding="utf-8") == "original\n"


def test_load_robot_positions_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    position_file = tmp_path / "positions.csv"
    position_file.write_text(
        "Calibration info\n"
        "\n"
        "1.0;2.0;3.0;image_0001.tif\n"
        "   \n"
        "4.5;5.5;6.5;image_0002.tif\n"
        "7;8;9;image_0003.tif\n",
        encoding="utf-8",
    )

    positions, image_names = load_robot_positions(position_file)

    np.testing.assert_allclose(
        positions,
        [[1.0, 2.0, 3.0], [4.5, 5.5, 6.5], [7.0, 8.0, 9.0]],
    )
    assert image_names == ["image_0001.tif", "image_0002.tif", "image_0003.tif"]


def test_load_robot_positions_reports_malformed_row(tmp_path: Path) -> None:
    position_file = tmp_path / "positions.csv"
    position_file.write_text("1.0;2.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        load_robot_positions(position_file)


def test_load_robot_positions_handles_empty_and_invalid_values(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("\n   \n", encoding="utf-8")

    positions, image_names = load_robot_positions(empty_file)

    assert positions.shape == (0, 3)
    assert image_names == []

    invalid_file = tmp_path / "invalid.csv"
    invalid_file.write_text("1.0;2.0;not-a-number\n", encoding="utf-8")
    with pytest.raises(ValueError, match="first three fields must be numeric"):
        load_robot_positions(invalid_file)

    no_image_file = tmp_path / "no-image.csv"
    no_image_file.write_text("1.0;2.0;3.0\n", encoding="utf-8")
    positions, image_names = load_robot_positions(no_image_file)
    np.testing.assert_allclose(positions, [[1.0, 2.0, 3.0]])
    assert image_names == []


def test_load_robot_positions_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        load_robot_positions(tmp_path / "missing.csv")


def test_search_images_uses_names_and_modified_time(tmp_path: Path) -> None:
    first = tmp_path / "first.tif"
    second = tmp_path / "second.tif"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    os.utime(first, (100.0, 100.0))
    os.utime(second, (200.0, 200.0))

    by_time = search_images(tmp_path, [])
    assert by_time == [first, second]

    unsorted = search_images(tmp_path, [], sort_by_mtime=False)
    assert set(unsorted) == {first, second}

    named = search_images(tmp_path, ["missing.tif", "first.tif"])
    assert named == [tmp_path / "missing.tif", first]


def test_calibration_document_includes_optional_session_metadata() -> None:
    document = calibration_document(
        nozzle_home_position=np.array([1.0, 2.0, 3.0]),
        intrinsic_matrix=np.eye(3),
        extrinsic_matrix=np.eye(4),
        distortion_coefficients=np.zeros(5),
        image_xy=(100, 200),
        n_distortion_coefs=5,
        rmse=0.25,
        observation_count=10,
        observations_used=8,
        sphere_home_position=np.array([4.0, 5.0, 6.0]),
        errors={"intrinsic_std": np.eye(3)},
        radial_scale={
            "radii": np.array([0.0, 0.1]),
            "scale": np.array([1.0, 0.99]),
        },
        session={"procedure_id": 7},
    )

    assert document["schema_version"] == RESULT_SCHEMA_VERSION
    assert document["session"] == {"procedure_id": 7}
    assert document["nozzle"]["home_position"] == pytest.approx([1.0, 2.0, 3.0])
    assert document["camera"]["resolution"] == [100, 200]
    assert document["camera"]["rmse"] == pytest.approx(0.25)
    assert document["camera"]["observations_used"] == 8
    assert document["camera"]["sphere_home_position"] == pytest.approx(
        [4.0, 5.0, 6.0]
    )
    np.testing.assert_allclose(
        document["camera"]["errors"]["intrinsic_std"],
        np.eye(3).tolist(),
    )
    assert document["camera"]["radial_scale"]["radii"] == pytest.approx(
        [0.0, 0.1]
    )
    assert document["camera"]["radial_scale"]["scale"] == pytest.approx(
        [1.0, 0.99]
    )


def test_calibration_document_rounds_values_to_their_uncertainty() -> None:
    intrinsic_matrix = np.array(
        [
            [14788.043071123456, 0.0, 1250.0000001],
            [0.0, 14783.061016987, 1000.0000002],
            [0.0, 0.0, 1.0],
        ]
    )
    extrinsic_matrix = np.array(
        [
            [0.999999, 0.001234, -0.000987, 315.487391203948],
            [-0.001233, 0.999998, 0.001111, -111.520987654321],
            [0.000988, -0.001110, 0.999999, -35.572123456789],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    document = calibration_document(
        nozzle_home_position=np.array([315.487391203948, -111.520987654321, -35.572123456789]),
        intrinsic_matrix=intrinsic_matrix,
        extrinsic_matrix=extrinsic_matrix,
        distortion_coefficients=np.array([-1.23456789012e-05, 2.3456789e-07]),
        image_xy=(2500, 2000),
        n_distortion_coefs=2,
        errors={
            "intrinsic_std": np.array(
                [
                    [0.123, 0.0, 0.08],
                    [0.0, 0.13, 0.0],
                    [0.0, 0.0, 0.0],
                ]
            ),
            "rot_vec_std": np.array([0.00031, 0.00028, 0.00041]),
            "tra_vec_std": np.array([0.021, 0.023, 0.019]),
            "distortion_std": np.array([3.1e-08, 2.7e-09]),
        },
    )

    camera = document["camera"]
    assert camera["intrinsic_matrix"][0][0] == pytest.approx(14788.04)
    assert camera["intrinsic_matrix"][1][1] == pytest.approx(14783.06)
    assert camera["errors"]["intrinsic_std"][0][0] == pytest.approx(0.12)
    assert camera["distortion_coefficients"][0] == pytest.approx(-1.2346e-05)
    assert camera["errors"]["distortion_std"][0] == pytest.approx(3.1e-08)
    # The extrinsic translation column shares the fitted translation errors.
    assert [row[3] for row in camera["extrinsic_matrix"][:3]] == pytest.approx(
        [315.487, -111.521, -35.572]
    )
    assert camera["errors"]["tra_vec_std"] == pytest.approx([0.021, 0.023, 0.019])
    # The rotation block keeps full precision: rot_vec_std does not describe
    # the rotation-matrix entries.
    assert camera["extrinsic_matrix"][0][0] == 0.999999
    assert camera["errors"]["rot_vec_std"] == pytest.approx([0.00031, 0.00028, 0.00041])


def test_calibration_document_rounds_nozzle_home_to_micrometres() -> None:
    document = calibration_document(
        nozzle_home_position=np.array([315.487391203948, -111.520987654321, -1.0e-05]),
        intrinsic_matrix=np.eye(3),
        extrinsic_matrix=np.eye(4),
        distortion_coefficients=np.zeros(1),
        image_xy=(2500, 2000),
    )

    assert document["nozzle"]["home_position"] == [315.487, -111.521, 0.0]


def test_calibration_document_keeps_full_precision_without_errors() -> None:
    document = calibration_document(
        nozzle_home_position=np.array([1.0, 2.0, 3.0]),
        intrinsic_matrix=np.array([[14788.043071123456, 0.0, 0.0]] * 3),
        extrinsic_matrix=np.eye(4),
        distortion_coefficients=np.array([-1.23456789012e-05]),
        image_xy=(100, 200),
    )

    assert document["camera"]["intrinsic_matrix"][0][0] == 14788.043071123456
    assert document["camera"]["distortion_coefficients"] == [-1.23456789012e-05]
    assert document["camera"]["errors"] is None


def test_calibration_document_rejects_mismatched_error_shapes() -> None:
    with pytest.raises(ValueError, match="does not match value shape"):
        calibration_document(
            nozzle_home_position=None,
            intrinsic_matrix=np.eye(3),
            extrinsic_matrix=np.eye(4),
            distortion_coefficients=np.zeros(1),
            image_xy=(100, 200),
            errors={"intrinsic_std": np.zeros(4)},
        )


def test_store_nozzle_uncertainty_writes_sidecar_json(tmp_path: Path) -> None:
    report_path = store_nozzle_uncertainty(
        report={
            "mode": "residual",
            "std": [0.01, 0.02, 0.03],
            "norm_std": 0.0374,
        },
        output_folder=tmp_path,
        filename="nozzle.json",
        metadata={
            "source": "example",
            "fit": {"observations_used": 10},
        },
    )

    assert report_path == tmp_path / "nozzle.json"
    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["schema_version"] == NOZZLE_UNCERTAINTY_SCHEMA_VERSION
    assert document["diagnostic"] == "nozzle_home_residual_bootstrap"
    assert document["source"] == "example"
    assert document["fit"] == {"observations_used": 10}
    assert document["mode"] == "residual"
    assert document["std"] == [0.01, 0.02, 0.03]
