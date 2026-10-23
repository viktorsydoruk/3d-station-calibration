"""Unit tests for station_calibration.settings.Settings."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from station_calibration.settings import Settings


# Minimal but complete config used by most tests. Values intentionally differ
# from config.toml so accidental fallback to the real file is visible.
BASE_CONFIG: dict[str, dict[str, Any]] = {
    "general": {
        "debug": False,
        "store_debug_images": False,
        "load_stored_data": True,
    },
    "general.files": {
        "robot_pos_filename": "robot_positions.csv",
        "output_folder": "output",
        "debug_folder": "debug",
        "all_center_points_filename": "all_points.dat",
        "image_name_patterns": ["*.tif", "*.tiff"],
        "sort_image_names_by_mtime": True,
    },
    "analysis": {
        "n_iterations": 3,
        "max_outliers": 0.25,
    },
    "analysis.background": {
        "fixed_bg_threshold": 30,
        "bg_height_pxs": 200,
        "bg_color_est_perc": 99.999,
    },
    "analysis.sphere_projection": {
        "n_move_aver": 11,
        "sphere_center_to_nozzle_part": 0.7,
        "min_bg_pixels_on_edges": 5,
        "blur_est_border_thickness": 2,
    },
    "analysis.fit": {
        "fix_cx_cy": True,
        "n_distortion_coefs": 4,
        "focal_length_initial": 1800.0,
        "camera_distance_initial": 95.0,
    },
}


def _toml_value(value: Any) -> str:
    """Serialize the small subset of TOML types used in these tests."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML test value: {value!r}")


def _write_config(path: Path, config: dict[str, dict[str, Any]]) -> None:
    """Write a nested dict as a TOML file without requiring a writer dependency."""
    lines: list[str] = []
    for section, values in config.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


@dataclass
class ConfigContext:
    """Temporary data folder plus editable TOML config for one test."""

    main_folder: Path
    config_file: Path
    config: dict[str, dict[str, Any]]

    def write(self) -> None:
        _write_config(self.config_file, self.config)

    def make(self, **options: Any) -> Settings:
        return Settings(
            self.main_folder,
            config_file=str(self.config_file),
            **options,
        )


@pytest.fixture
def context(tmp_path: Path) -> ConfigContext:
    """Create an isolated main folder and config for a single test."""
    main_folder = tmp_path / "data"
    main_folder.mkdir()

    ctx = ConfigContext(
        main_folder=main_folder,
        config_file=tmp_path / "config.toml",
        config=copy.deepcopy(BASE_CONFIG),
    )
    ctx.write()
    return ctx


# ----------------------------------------------------------------------
# Config loading and config-file selection
# ----------------------------------------------------------------------


def test_loads_values_from_config(context: ConfigContext) -> None:
    settings = context.make()

    assert settings.config_file_path == context.config_file
    assert settings.debug is False
    assert settings.store_debug_images is False
    assert settings.load_stored_data is True

    assert settings.robot_pos_file == context.main_folder / "robot_positions.csv"
    assert settings.output_folder == context.main_folder / "output"
    assert settings.output_folder.is_dir()
    assert settings.debug_folder == context.main_folder / "debug"
    assert settings.debug_folder.is_dir()
    assert (
        settings.all_center_points_file
        == settings.output_folder / "all_points.dat"
    )
    assert settings.image_name_patterns == ("*.tif", "*.tiff")
    assert settings.sort_imagenames_by_mtime is True

    assert settings.n_iterations == 3
    assert settings.allowed_outliers == 0.25
    assert settings.fixed_bg_threshold == 30.0
    assert settings.bg_height_pxs == 200
    assert settings.bg_color_est_perc == 99.999
    assert settings.n_move_aver == 11
    assert settings.sphere_center_to_nozzle_part == 0.7
    assert settings.min_bg_pixels_on_edges == 5
    assert settings.blur_est_border_thickness == 2
    assert settings.fix_cx_cy is True
    assert settings.n_distortion_coefs == 4
    assert settings.focal_length_initial == 1800.0
    assert settings.camera_distance_initial == 95.0
    assert settings.target_observations == 500
    assert settings.max_observations is None

    # The parsed config is exposed as well.
    assert settings.config["analysis"]["n_iterations"] == 3


def test_default_config_file_is_absolute_and_exists() -> None:
    assert Settings.DEFAULT_CONFIG_FILE.is_absolute()
    assert Settings.DEFAULT_CONFIG_FILE.is_file()
    assert Settings.DEFAULT_CONFIG_FILE.parent.name == "resources"
    assert Settings.DEFAULT_CONFIG_FILE.name == "config.toml"


def test_loads_default_config_without_explicit_file(context: ConfigContext) -> None:
    settings = Settings(context.main_folder)

    assert settings.config_file_path == Settings.DEFAULT_CONFIG_FILE
    assert settings.config_file_path.is_absolute()
    assert settings.target_observations == 500


def test_loads_stop_settings_and_overrides(context: ConfigContext) -> None:
    context.config["analysis.stop"] = {
        "target_observations": 321,
        "max_observations": 450,
    }
    context.write()

    settings = context.make()
    assert settings.target_observations == 321
    assert settings.max_observations == 450

    overridden = context.make(target_observations=200, max_observations=250)
    assert overridden.target_observations == 200
    assert overridden.max_observations == 250


def test_invalid_stop_settings_raise(context: ConfigContext) -> None:
    context.config["analysis.stop"] = {"target_observations": 0}
    context.write()

    with pytest.raises(ValueError, match="target_observations"):
        context.make()

    context.config["analysis.stop"] = {
        "target_observations": 500,
        "max_observations": 0,
    }
    context.write()

    with pytest.raises(ValueError, match="max_observations"):
        context.make()


def test_config_file_accepts_string_and_path(context: ConfigContext) -> None:
    from_string = Settings(context.main_folder, config_file=str(context.config_file))
    from_path = Settings(context.main_folder, config_file=context.config_file)

    assert from_string.config_file_path == context.config_file
    assert from_path.config_file_path == context.config_file


def test_missing_config_file_raises(context: ConfigContext) -> None:
    missing = context.config_file.parent / "missing.toml"

    with pytest.raises(FileNotFoundError):
        Settings(context.main_folder, config_file=str(missing))


def test_empty_config_file_raises(context: ConfigContext) -> None:
    with pytest.raises(ValueError):
        Settings(context.main_folder, config_file="   ")


def test_invalid_config_file_type_raises(context: ConfigContext) -> None:
    with pytest.raises(TypeError):
        Settings(context.main_folder, config_file=123)  # type: ignore[arg-type]


def test_unknown_option_raises(context: ConfigContext) -> None:
    with pytest.raises(ValueError, match="Unknown settings: unknown_option"):
        context.make(unknown_option=1)  # type: ignore[call-arg]


# ----------------------------------------------------------------------
# Path properties
# ----------------------------------------------------------------------


def test_debug_folder_exists_even_when_debug_is_disabled(
    context: ConfigContext,
) -> None:
    settings = context.make(debug=False)

    assert settings.debug is False
    assert settings.debug_folder.is_dir()
    assert settings.debug_folder == context.main_folder / "debug"


def test_paths_are_resolved_below_main_folder(context: ConfigContext) -> None:
    settings = context.make(
        robot_pos_file=Path("positions.csv"),
        output_folder=Path("results"),
        debug_folder=Path("dbg"),
        all_center_points_file=Path("points.tsv"),
    )

    assert settings.robot_pos_file == context.main_folder / "positions.csv"
    assert settings.output_folder == context.main_folder / "results"
    assert settings.debug_folder == context.main_folder / "dbg"
    assert (
        settings.all_center_points_file
        == context.main_folder / "results" / "points.tsv"
    )
    assert settings.output_folder.is_dir()
    assert settings.debug_folder.is_dir()


def test_property_setters_update_paths_and_values(context: ConfigContext) -> None:
    settings = context.make()

    settings.robot_pos_file = "new_positions.csv"
    settings.output_folder = "new_output"
    settings.debug_folder = "new_debug"
    settings.all_center_points_file = "new_points.dat"
    settings.image_name_patterns = "*.png"
    settings.n_distortion_coefs = 14

    assert settings.robot_pos_file == context.main_folder / "new_positions.csv"
    assert settings.output_folder == context.main_folder / "new_output"
    assert settings.debug_folder == context.main_folder / "new_debug"
    assert (
        settings.all_center_points_file
        == context.main_folder / "new_output" / "new_points.dat"
    )
    assert settings.output_folder.is_dir()
    assert settings.debug_folder.is_dir()
    assert settings.image_name_patterns == ("*.png",)
    assert settings.n_distortion_coefs == 14

    with pytest.raises(ValueError):
        settings.n_distortion_coefs = 3


# ----------------------------------------------------------------------
# Keyword option overrides
# ----------------------------------------------------------------------


def test_public_option_names_override_toml_keys(context: ConfigContext) -> None:
    settings = context.make(
        robot_pos_file="override.csv",
        all_center_points_file="override.dat",
        allowed_outliers=2,
        sort_imagenames_by_mtime=False,
        n_iterations=5,
        image_name_patterns="*.png",
        n_distortion_coefs=8,
        focal_length_initial=1500.0,
        camera_distance_initial=120.0,
        fix_cx_cy=False,
        debug=True,
        store_debug_images=True,
        load_stored_data=False,
        bg_height_pxs=123,
    )

    assert settings.robot_pos_file == context.main_folder / "override.csv"
    assert settings.all_center_points_file == settings.output_folder / "override.dat"
    assert settings.allowed_outliers == 2.0
    assert settings.sort_imagenames_by_mtime is False
    assert settings.n_iterations == 5
    assert settings.image_name_patterns == ("*.png",)
    assert settings.n_distortion_coefs == 8
    assert settings.focal_length_initial == 1500.0
    assert settings.camera_distance_initial == 120.0
    assert settings.fix_cx_cy is False
    assert settings.debug is True
    assert settings.store_debug_images is True
    assert settings.load_stored_data is False
    assert settings.bg_height_pxs == 123


def test_image_name_patterns_are_normalized_to_tuple(context: ConfigContext) -> None:
    settings = context.make()

    assert settings.image_name_patterns == ("*.tif", "*.tiff")

    settings.image_name_patterns = "*.png"
    assert settings.image_name_patterns == ("*.png",)

    settings.image_name_patterns = ["*.jpg", "*.jpeg"]  # type: ignore[assignment]
    assert settings.image_name_patterns == ("*.jpg", "*.jpeg")


def test_optional_settings_use_defaults(context: ConfigContext) -> None:
    for key in ("debug", "store_debug_images", "load_stored_data"):
        context.config["general"].pop(key)
    for key in ("image_name_patterns", "sort_image_names_by_mtime"):
        context.config["general.files"].pop(key)
    for key in (
        "fix_cx_cy",
        "n_distortion_coefs",
        "focal_length_initial",
        "camera_distance_initial",
    ):
        context.config["analysis.fit"].pop(key)
    context.write()

    settings = context.make()

    assert settings.debug is False
    assert settings.store_debug_images is False
    assert settings.load_stored_data is False
    assert settings.image_name_patterns == ("*.tif", "*.tiff")
    assert settings.sort_imagenames_by_mtime is True
    assert settings.fix_cx_cy is True
    assert settings.n_distortion_coefs == 0
    assert settings.focal_length_initial == 2000.0
    assert settings.camera_distance_initial == 80.0


# ----------------------------------------------------------------------
# Config structure errors
# ----------------------------------------------------------------------


def test_missing_section_raises_clear_error(context: ConfigContext) -> None:
    del context.config["analysis.background"]
    context.write()

    with pytest.raises(KeyError, match=r"analysis\.background"):
        context.make()


def test_missing_required_setting_raises_clear_error(
    context: ConfigContext,
) -> None:
    del context.config["analysis"]["n_iterations"]
    context.write()

    with pytest.raises(KeyError, match="n_iterations"):
        context.make()


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize("value", Settings.VALID_DISTORTION_COEFS)
def test_n_distortion_coefs_accepts_supported_values(
    context: ConfigContext,
    value: int,
) -> None:
    context.config["analysis.fit"]["n_distortion_coefs"] = value
    context.write()

    settings = context.make()

    assert settings.n_distortion_coefs == value


@pytest.mark.parametrize("value", [-1, 1, 3, 7, 13, 15])
def test_n_distortion_coefs_rejects_unsupported_values(
    context: ConfigContext,
    value: int,
) -> None:
    context.config["analysis.fit"]["n_distortion_coefs"] = value
    context.write()

    with pytest.raises(ValueError, match="n_distortion_coefs"):
        context.make()


@pytest.mark.parametrize(
    ("section", "key", "value", "expected_message"),
    [
        ("analysis", "n_iterations", 0, "n_iterations"),
        ("analysis", "max_outliers", -0.1, "allowed_outliers"),
        ("analysis.background", "fixed_bg_threshold", -1, "fixed_bg_threshold"),
        ("analysis.background", "bg_height_pxs", 0, "bg_height_pxs"),
        ("analysis.background", "bg_color_est_perc", 0, "bg_color_est_perc"),
        ("analysis.background", "bg_color_est_perc", 100.1, "bg_color_est_perc"),
        ("analysis.sphere_projection", "n_move_aver", 0, "n_move_aver"),
        (
            "analysis.sphere_projection",
            "sphere_center_to_nozzle_part",
            -0.01,
            "sphere_center_to_nozzle_part",
        ),
        (
            "analysis.sphere_projection",
            "sphere_center_to_nozzle_part",
            1.01,
            "sphere_center_to_nozzle_part",
        ),
        (
            "analysis.sphere_projection",
            "min_bg_pixels_on_edges",
            0,
            "min_bg_pixels_on_edges",
        ),
        (
            "analysis.sphere_projection",
            "blur_est_border_thickness",
            0,
            "blur_est_border_thickness",
        ),
        ("analysis.fit", "focal_length_initial", 0, "focal_length_initial"),
        ("analysis.fit", "focal_length_initial", -1, "focal_length_initial"),
        ("analysis.fit", "camera_distance_initial", 0, "camera_distance_initial"),
        ("analysis.fit", "camera_distance_initial", -1, "camera_distance_initial"),
    ],
)
def test_invalid_values_raise(
    context: ConfigContext,
    section: str,
    key: str,
    value: float,
    expected_message: str,
) -> None:
    context.config[section][key] = value
    context.write()

    with pytest.raises(ValueError, match=expected_message):
        context.make()


def test_boundary_values_are_accepted(context: ConfigContext) -> None:
    context.config["analysis"]["n_iterations"] = 1
    context.config["analysis"]["max_outliers"] = 0
    context.config["analysis.background"]["fixed_bg_threshold"] = 0
    context.config["analysis.background"]["bg_color_est_perc"] = 100
    context.config["analysis.fit"]["n_distortion_coefs"] = 0
    context.write()

    settings = context.make()

    assert settings.n_iterations == 1
    assert settings.allowed_outliers == 0.0
    assert settings.fixed_bg_threshold == 0.0
    assert settings.bg_color_est_perc == 100.0
    assert settings.n_distortion_coefs == 0


@pytest.mark.parametrize("part", [0, 1])
def test_sphere_center_to_nozzle_part_boundaries_are_accepted(
    context: ConfigContext,
    part: int,
) -> None:
    context.config["analysis.sphere_projection"][
        "sphere_center_to_nozzle_part"
    ] = part
    context.write()

    settings = context.make()

    assert settings.sphere_center_to_nozzle_part == float(part)
