# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for point-cache storage."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from station_calibration.storage import (
    load_all_points,
    load_robot_positions,
    search_images,
    store_all_points,
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
