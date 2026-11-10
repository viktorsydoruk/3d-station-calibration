# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

""" Here is the settings class for 3D station calibration software

    This class consists all the parameters needed to properly run all parts of calibration routine.
    It consists two groups of parameters: one group can be changed only through the config.toml file, when another
    though the keywords arguments given to the class during its initialization

    created 31.08.2026
"""


__all__ = ['Settings', 'PossibleOptions']

import math
import tomllib
from pathlib import Path
from typing import Any
from typing import TypedDict
from typing import Unpack

from .models import DEFAULT_LOSS_F_SCALE
from .readiness import (
    DEFAULT_READINESS_CHECKPOINT_INTERVAL,
    DEFAULT_READINESS_DISTORTION_TOLERANCE,
    DEFAULT_READINESS_ENABLED,
    DEFAULT_READINESS_FOCAL_RELATIVE_TOLERANCE,
    DEFAULT_READINESS_HOME_TOLERANCE_MM,
    DEFAULT_READINESS_MIN_INLIER_FRACTION,
    DEFAULT_READINESS_PRINCIPAL_POINT_TOLERANCE_PX,
    DEFAULT_READINESS_ROTATION_TOLERANCE_DEG,
    DEFAULT_READINESS_STABLE_CHECKPOINTS,
    DEFAULT_READINESS_TRANSLATION_TOLERANCE_MM,
)
from .stop import DEFAULT_TARGET_OBSERVATIONS


_MISSING = object()

DEFAULT_UNCERTAINTY_ENABLED = False
DEFAULT_UNCERTAINTY_N_BOOTSTRAP = 500
DEFAULT_UNCERTAINTY_SEED = 0
DEFAULT_UNCERTAINTY_REPORT_FILENAME = "nozzle_uncertainty.json"


def _finite_float(value: Any, name: str) -> float:
    """Convert a setting to float and reject NaN/infinity."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, got {result}")
    return result


class PossibleOptions(TypedDict, total=False):
    """
        Optional keyword arguments that override values from config.toml.

        Names follow the public attributes of Settings. Where the TOML key differs
        (for example ``robot_pos_filename`` vs ``robot_pos_file``), the mapping is
        done in Settings._get.
    """
    config_file: str | Path
    debug: bool
    store_debug_images: bool
    archive_sessions: bool
    robot_pos_file: str | Path
    output_folder: str | Path
    debug_folder: str | Path
    all_center_points_file: str | Path
    load_stored_data: bool
    image_name_patterns: tuple[str, ...] | str
    sort_imagenames_by_mtime: bool

    bg_height_pxs: int
    bg_color_est_perc: float
    bg_threshold_method: str
    bg_noise_sigma: float
    fixed_bg_threshold: float
    n_move_aver: int
    sphere_center_to_nozzle_part: float
    min_bg_pixels_on_edges: int
    blur_est_border_thickness: int
    subpixel_edges: bool
    subpixel_max_n_sigma: float | None
    fix_cx_cy: bool
    n_distortion_coefs: int
    focal_length_initial: float
    camera_distance_initial: float
    loss_f_scale: float
    center_weighting: bool
    n_iterations: int
    allowed_outliers: float
    outlier_confidence: float
    outlier_cluster_guard: bool
    target_observations: int
    max_observations: int | None
    fit_every_n: int | None
    readiness_enabled: bool
    readiness_checkpoint_interval: int
    readiness_stable_checkpoints: int
    readiness_min_inlier_fraction: float
    readiness_focal_relative_tolerance: float
    readiness_principal_point_tolerance_px: float
    readiness_translation_tolerance_mm: float
    readiness_rotation_tolerance_deg: float
    readiness_home_tolerance_mm: float
    readiness_distortion_tolerance: float
    uncertainty_enabled: bool
    uncertainty_n_bootstrap: int
    uncertainty_seed: int
    uncertainty_report_filename: str | Path


class Settings:
    """
        Settings class to configure 3D station calibration software
    """
    # Class-level defaults
    DEFAULT_CONFIG_FILE = Path(__file__).resolve().parent / "resources" / "config.toml"
    VALID_DISTORTION_COEFS = (0, 4, 5, 8, 12, 14)

    config_file_path: Path
    config: dict[str, Any]
    _opts: dict[str, Any]
    debug: bool
    store_debug_images: bool
    archive_sessions: bool
    _robot_pos_file: Path
    _all_center_points_file: Path
    _output_folder: Path
    _debug_folder: Path
    load_stored_data: bool
    _image_name_patterns: tuple[str, ...]
    sort_imagenames_by_mtime: bool

    bg_height_pxs: int
    bg_color_est_perc: float
    bg_threshold_method: str
    bg_noise_sigma: float
    fixed_bg_threshold: float
    n_move_aver: int
    sphere_center_to_nozzle_part: float
    min_bg_pixels_on_edges: int
    blur_est_border_thickness: int
    subpixel_edges: bool
    subpixel_max_n_sigma: float | None
    fix_cx_cy: bool
    _n_distortion_coefs: int
    focal_length_initial: float
    camera_distance_initial: float
    loss_f_scale: float
    center_weighting: bool

    n_iterations: int
    allowed_outliers: float
    outlier_confidence: float
    outlier_cluster_guard: bool
    target_observations: int
    max_observations: int | None
    fit_every_n: int | None
    readiness_enabled: bool
    readiness_checkpoint_interval: int
    readiness_stable_checkpoints: int
    readiness_min_inlier_fraction: float
    readiness_focal_relative_tolerance: float
    readiness_principal_point_tolerance_px: float
    readiness_translation_tolerance_mm: float
    readiness_rotation_tolerance_deg: float
    readiness_home_tolerance_mm: float
    readiness_distortion_tolerance: float
    uncertainty_enabled: bool
    uncertainty_n_bootstrap: int
    uncertainty_seed: int
    uncertainty_report_filename: str

    def __init__(self,
                 folder_to_analyze: str | Path,
                 **opts: Unpack[PossibleOptions]
                 ):

        #
        # Defining all the parameters
        #
        self.main_folder = Path(folder_to_analyze)  # should be defined first
        self._opts = dict(opts)

        # Validate unknown keys
        unknown_keys = set(self._opts) - set(PossibleOptions.__annotations__.keys())
        if unknown_keys:
            raise ValueError(
                f"Unknown settings: {', '.join(sorted(unknown_keys))}"
            )

        # Load config file
        self.config_file_path = self._resolve_config_file()
        if not self.config_file_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file_path.absolute()}")

        with self.config_file_path.open('rb') as f:
            self.config = tomllib.load(f)

        # Initialize all settings (properties handle path transformations)
        self._init_general()  # should be always first initialized
        self._init_files()
        self._init_analysis()
        self._init_background()
        self._init_sphere_projection()
        self._init_fit()
        self._init_stop()
        self._init_readiness()
        self._init_uncertainty()

    # -----------------------------------------------------------------
    # Initialization helpers
    # -----------------------------------------------------------------

    def _resolve_config_file(self) -> Path:
        """Return the explicitly given config file or the default one from the package."""
        config_file = self._opts.get("config_file")
        if config_file is None:
            return self.DEFAULT_CONFIG_FILE

        if isinstance(config_file, Path):
            return config_file.expanduser()

        if not isinstance(config_file, str):
            raise TypeError("config_file must be a string or pathlib.Path")

        if not config_file.strip():
            raise ValueError("config_file must not be empty")

        return Path(config_file).expanduser()

    def _section(self, *keys: str) -> dict[str, Any]:
        """Return a nested config section and raise a clear error if it is missing."""
        section: Any = self.config
        path: list[str] = []
        for key in keys:
            path.append(key)
            if not isinstance(section, dict) or key not in section:
                section_name = ".".join(path)
                raise KeyError(
                    f"Missing config section '[{section_name}]' in {self.config_file_path}"
                )
            section = section[key]

        if not isinstance(section, dict):
            section_name = ".".join(path)
            raise TypeError(
                f"Config section '[{section_name}]' in {self.config_file_path} is not a table"
            )

        return section

    def _get(self,
             section: dict[str, Any],
             key: str,
             default: Any = _MISSING,
             override: str | None = None) -> Any:
        """
            Get value from section, optionally overridden by __init__ kwargs.

            ``override`` is the public Settings attribute name when it differs from
            the TOML key (e.g. ``robot_pos_file`` for ``robot_pos_filename``).

        :param section: section read from toml file
        :param key: key to read value
        :param default: default value
        :param override: name of the keyword argument that overrides this key
        :return: value
        """
        # Check if there's a runtime override
        if override is not None:
            value = self._opts.get(override)
            if value is not None:
                return value

        # Also check an option with the same name as the TOML key
        value = self._opts.get(key)
        if value is not None:
            return value

        # Fall back to config file
        if default is _MISSING:
            if key not in section:
                raise KeyError(
                    f"Missing required setting '{key}' in {self.config_file_path}"
                )
            return section[key]

        return section.get(key, default)

    def _init_general(self) -> None:
        general = self._section("general")
        self.debug = bool(self._get(general, 'debug', False))
        self.store_debug_images = bool(self._get(general, 'store_debug_images', False))
        self.archive_sessions = bool(self._get(general, 'archive_sessions', True))
        self.load_stored_data = bool(self._get(general, 'load_stored_data', False))

    def _init_files(self) -> None:
        files = self._section("general", "files")
        self.robot_pos_file = self._get(files, "robot_pos_filename", override="robot_pos_file")
        self.output_folder = self._get(files, "output_folder")
        self.debug_folder = self._get(files, "debug_folder")
        self.all_center_points_file = self._get(
            files, "all_center_points_filename", override="all_center_points_file"
        )
        self.image_name_patterns = self._get(
            files, "image_name_patterns", default=("*.tif", "*.tiff")
        )
        self.sort_imagenames_by_mtime = bool(self._get(
            files, "sort_image_names_by_mtime",
            override="sort_imagenames_by_mtime",
            default=True,
        ))

    def _init_analysis(self) -> None:
        analysis = self._section("analysis")
        self.n_iterations = int(self._get(analysis, "n_iterations"))
        self.allowed_outliers = _finite_float(
            self._get(analysis, "max_outliers", override="allowed_outliers"),
            "allowed_outliers (max_outliers)",
        )
        self.outlier_confidence = _finite_float(
            self._get(analysis, "outlier_confidence", 0.999),
            "outlier_confidence",
        )
        self.outlier_cluster_guard = bool(
            self._get(analysis, "outlier_cluster_guard", True)
        )
        fit_every_n = int(self._get(analysis, "fit_every_n", 1))

        if self.n_iterations < 1:
            raise ValueError(f"n_iterations must be at least 1, got {self.n_iterations}")
        if self.allowed_outliers < 0:
            raise ValueError(
                f"allowed_outliers (max_outliers) must be non-negative, got {self.allowed_outliers}"
            )
        if not 0.0 < self.outlier_confidence < 1.0:
            raise ValueError(
                "outlier_confidence must be strictly between 0 and 1, got "
                f"{self.outlier_confidence}"
            )
        if fit_every_n < 0:
            raise ValueError(
                f"fit_every_n must be non-negative, got {fit_every_n}"
            )
        self.fit_every_n = None if fit_every_n == 0 else fit_every_n

    def _init_background(self) -> None:
        bg = self._section("analysis", "background")
        self.fixed_bg_threshold = _finite_float(
            self._get(bg, "fixed_bg_threshold"),
            "fixed_bg_threshold",
        )
        self.bg_height_pxs = int(self._get(bg, "bg_height_pxs"))
        self.bg_color_est_perc = _finite_float(
            self._get(bg, "bg_color_est_perc"),
            "bg_color_est_perc",
        )
        method = self._get(bg, "bg_threshold_method", "percentile")
        if not isinstance(method, str):
            raise TypeError(
                f"bg_threshold_method must be a string, got {type(method).__name__}"
            )
        self.bg_threshold_method = method.strip().lower()
        self.bg_noise_sigma = _finite_float(
            self._get(bg, "bg_noise_sigma", 5.0),
            "bg_noise_sigma",
        )

        if self.fixed_bg_threshold < 0:
            raise ValueError(
                f"fixed_bg_threshold must be non-negative, got {self.fixed_bg_threshold}"
            )
        if self.bg_height_pxs < 10:
            raise ValueError(
                f"bg_height_pxs must be at least 10, got {self.bg_height_pxs}"
            )
        if not 0 < self.bg_color_est_perc <= 100:
            raise ValueError(
                f"bg_color_est_perc must be in (0, 100], got {self.bg_color_est_perc}"
            )
        if self.bg_threshold_method not in ("mad", "percentile"):
            raise ValueError(
                "bg_threshold_method must be 'mad' or 'percentile', "
                f"got {self.bg_threshold_method!r}"
            )
        if self.bg_noise_sigma <= 0:
            raise ValueError(
                f"bg_noise_sigma must be positive, got {self.bg_noise_sigma}"
            )

    def _init_sphere_projection(self) -> None:
        sphere = self._section("analysis", "sphere_projection")
        self.n_move_aver = int(self._get(sphere, "n_move_aver"))
        self.sphere_center_to_nozzle_part = _finite_float(
            self._get(sphere, "sphere_center_to_nozzle_part"),
            "sphere_center_to_nozzle_part",
        )
        self.min_bg_pixels_on_edges = int(self._get(sphere, "min_bg_pixels_on_edges"))
        self.blur_est_border_thickness = int(self._get(sphere, "blur_est_border_thickness"))
        self.subpixel_edges = bool(self._get(sphere, "subpixel_edges", False))
        max_n_sigma = self._get(sphere, "subpixel_max_n_sigma", 0.25)
        self.subpixel_max_n_sigma = (
            None
            if max_n_sigma is None
            else _finite_float(max_n_sigma, "subpixel_max_n_sigma")
        )

        if self.n_move_aver < 1:
            raise ValueError(f"n_move_aver must be at least 1, got {self.n_move_aver}")
        if not 0 <= self.sphere_center_to_nozzle_part <= 1:
            raise ValueError(
                "sphere_center_to_nozzle_part must be between 0 and 1, got "
                f"{self.sphere_center_to_nozzle_part}"
            )
        if self.min_bg_pixels_on_edges < 1:
            raise ValueError(
                "min_bg_pixels_on_edges must be at least 1, got "
                f"{self.min_bg_pixels_on_edges}"
            )
        if self.blur_est_border_thickness < 1:
            raise ValueError(
                "blur_est_border_thickness must be at least 1, got "
                f"{self.blur_est_border_thickness}"
            )
        if (
            self.subpixel_max_n_sigma is not None
            and self.subpixel_max_n_sigma < 0
        ):
            raise ValueError(
                "subpixel_max_n_sigma must be non-negative, got "
                f"{self.subpixel_max_n_sigma}"
            )

    def _init_fit(self) -> None:
        fit = self._section("analysis", "fit")
        self.fix_cx_cy = bool(self._get(fit, "fix_cx_cy", True))
        self.n_distortion_coefs = self._get(fit, "n_distortion_coefs", 0)
        self.focal_length_initial = _finite_float(
            self._get(fit, "focal_length_initial", 2000.0),
            "focal_length_initial",
        )
        self.camera_distance_initial = _finite_float(
            self._get(fit, "camera_distance_initial", 80.0),
            "camera_distance_initial",
        )
        self.loss_f_scale = _finite_float(
            self._get(fit, "loss_f_scale", DEFAULT_LOSS_F_SCALE),
            "loss_f_scale",
        )
        self.center_weighting = bool(self._get(fit, "center_weighting", True))

        if self.focal_length_initial <= 0:
            raise ValueError(
                "focal_length_initial must be positive, got "
                f"{self.focal_length_initial}"
            )
        if self.camera_distance_initial <= 0:
            raise ValueError(
                "camera_distance_initial must be positive, got "
                f"{self.camera_distance_initial}"
            )
        if self.loss_f_scale <= 0:
            raise ValueError(
                f"loss_f_scale must be positive, got {self.loss_f_scale}"
            )

    def _init_stop(self) -> None:
        analysis = self._section("analysis")
        stop = analysis.get("stop", {})
        if not isinstance(stop, dict):
            raise TypeError(
                "Config section '[analysis.stop]' "
                f"in {self.config_file_path} is not a table"
            )

        self.target_observations = int(
            self._get(stop, "target_observations", DEFAULT_TARGET_OBSERVATIONS)
        )
        max_observations = self._get(stop, "max_observations", None)
        self.max_observations = (
            None if max_observations is None else int(max_observations)
        )

        if self.target_observations < 1:
            raise ValueError(
                "target_observations must be positive, got "
                f"{self.target_observations}"
            )
        if self.max_observations is not None and self.max_observations < 1:
            raise ValueError(
                "max_observations must be positive or unset, got "
                f"{self.max_observations}"
            )

    def _init_readiness(self) -> None:
        analysis = self._section("analysis")
        readiness = analysis.get("readiness", {})
        if not isinstance(readiness, dict):
            raise TypeError(
                "Config section '[analysis.readiness]' "
                f"in {self.config_file_path} is not a table"
            )

        self.readiness_enabled = bool(
            self._get(
                readiness,
                "enabled",
                DEFAULT_READINESS_ENABLED,
                override="readiness_enabled",
            )
        )
        self.readiness_checkpoint_interval = int(
            self._get(
                readiness,
                "checkpoint_interval",
                DEFAULT_READINESS_CHECKPOINT_INTERVAL,
                override="readiness_checkpoint_interval",
            )
        )
        self.readiness_stable_checkpoints = int(
            self._get(
                readiness,
                "stable_checkpoints",
                DEFAULT_READINESS_STABLE_CHECKPOINTS,
                override="readiness_stable_checkpoints",
            )
        )
        self.readiness_min_inlier_fraction = _finite_float(
            self._get(
                readiness,
                "min_inlier_fraction",
                DEFAULT_READINESS_MIN_INLIER_FRACTION,
                override="readiness_min_inlier_fraction",
            ),
            "readiness_min_inlier_fraction",
        )
        self.readiness_focal_relative_tolerance = _finite_float(
            self._get(
                readiness,
                "focal_relative_tolerance",
                DEFAULT_READINESS_FOCAL_RELATIVE_TOLERANCE,
                override="readiness_focal_relative_tolerance",
            ),
            "readiness_focal_relative_tolerance",
        )
        self.readiness_principal_point_tolerance_px = _finite_float(
            self._get(
                readiness,
                "principal_point_tolerance_px",
                DEFAULT_READINESS_PRINCIPAL_POINT_TOLERANCE_PX,
                override="readiness_principal_point_tolerance_px",
            ),
            "readiness_principal_point_tolerance_px",
        )
        self.readiness_translation_tolerance_mm = _finite_float(
            self._get(
                readiness,
                "translation_tolerance_mm",
                DEFAULT_READINESS_TRANSLATION_TOLERANCE_MM,
                override="readiness_translation_tolerance_mm",
            ),
            "readiness_translation_tolerance_mm",
        )
        self.readiness_rotation_tolerance_deg = _finite_float(
            self._get(
                readiness,
                "rotation_tolerance_deg",
                DEFAULT_READINESS_ROTATION_TOLERANCE_DEG,
                override="readiness_rotation_tolerance_deg",
            ),
            "readiness_rotation_tolerance_deg",
        )
        self.readiness_home_tolerance_mm = _finite_float(
            self._get(
                readiness,
                "home_tolerance_mm",
                DEFAULT_READINESS_HOME_TOLERANCE_MM,
                override="readiness_home_tolerance_mm",
            ),
            "readiness_home_tolerance_mm",
        )
        self.readiness_distortion_tolerance = _finite_float(
            self._get(
                readiness,
                "distortion_tolerance",
                DEFAULT_READINESS_DISTORTION_TOLERANCE,
                override="readiness_distortion_tolerance",
            ),
            "readiness_distortion_tolerance",
        )

        if self.readiness_checkpoint_interval < 1:
            raise ValueError(
                "readiness_checkpoint_interval must be positive, got "
                f"{self.readiness_checkpoint_interval}"
            )
        if self.readiness_stable_checkpoints < 1:
            raise ValueError(
                "readiness_stable_checkpoints must be positive, got "
                f"{self.readiness_stable_checkpoints}"
            )
        if not 0.0 < self.readiness_min_inlier_fraction <= 1.0:
            raise ValueError(
                "readiness_min_inlier_fraction must be in (0, 1], got "
                f"{self.readiness_min_inlier_fraction}"
            )
        for name, value in (
            (
                "readiness_focal_relative_tolerance",
                self.readiness_focal_relative_tolerance,
            ),
            (
                "readiness_principal_point_tolerance_px",
                self.readiness_principal_point_tolerance_px,
            ),
            (
                "readiness_translation_tolerance_mm",
                self.readiness_translation_tolerance_mm,
            ),
            (
                "readiness_rotation_tolerance_deg",
                self.readiness_rotation_tolerance_deg,
            ),
            (
                "readiness_home_tolerance_mm",
                self.readiness_home_tolerance_mm,
            ),
            (
                "readiness_distortion_tolerance",
                self.readiness_distortion_tolerance,
            ),
        ):
            if value <= 0.0:
                raise ValueError(f"{name} must be positive, got {value}")

    def _init_uncertainty(self) -> None:
        analysis = self._section("analysis")
        uncertainty = analysis.get("uncertainty", {})
        if not isinstance(uncertainty, dict):
            raise TypeError(
                "Config section '[analysis.uncertainty]' "
                f"in {self.config_file_path} is not a table"
            )

        self.uncertainty_enabled = bool(
            self._get(
                uncertainty,
                "enabled",
                DEFAULT_UNCERTAINTY_ENABLED,
                override="uncertainty_enabled",
            )
        )
        self.uncertainty_n_bootstrap = int(
            self._get(
                uncertainty,
                "n_bootstrap",
                DEFAULT_UNCERTAINTY_N_BOOTSTRAP,
                override="uncertainty_n_bootstrap",
            )
        )
        self.uncertainty_seed = int(
            self._get(
                uncertainty,
                "seed",
                DEFAULT_UNCERTAINTY_SEED,
                override="uncertainty_seed",
            )
        )
        report_filename = self._get(
            uncertainty,
            "report_filename",
            DEFAULT_UNCERTAINTY_REPORT_FILENAME,
            override="uncertainty_report_filename",
        )
        if not isinstance(report_filename, (str, Path)):
            raise TypeError(
                "uncertainty_report_filename must be a string or pathlib.Path"
            )
        report_filename = str(report_filename).strip()
        if not report_filename:
            raise ValueError("uncertainty_report_filename must not be empty")
        self.uncertainty_report_filename = report_filename

        if self.uncertainty_n_bootstrap < 1:
            raise ValueError(
                "uncertainty_n_bootstrap must be positive, got "
                f"{self.uncertainty_n_bootstrap}"
            )
        if self.uncertainty_seed < 0:
            raise ValueError(
                "uncertainty_seed must be non-negative, got "
                f"{self.uncertainty_seed}"
            )

    # -----------------------------------------------------------------
    # Properties with validation/transformation
    # -----------------------------------------------------------------

    @property
    def robot_pos_file(self) -> Path:
        return self._robot_pos_file

    @robot_pos_file.setter
    def robot_pos_file(self, value: str | Path):
        self._robot_pos_file = self.main_folder.joinpath(value)

    @property
    def output_folder(self) -> Path:
        """"""
        return self._output_folder

    @output_folder.setter
    def output_folder(self, value: str | Path):
        self._output_folder = self.main_folder.joinpath(value)
        self._output_folder.mkdir(parents=True, exist_ok=True)

    @property
    def debug_folder(self) -> Path:
        """"""
        return self._debug_folder

    @debug_folder.setter
    def debug_folder(self, value: str | Path):
        # The folder is used not only for optional debug images: failure images are
        # written there even when debug output is disabled. It must therefore always
        # be a valid Path, not only when debug/store_debug_images is enabled.
        self._debug_folder = self.main_folder.joinpath(value)
        self._debug_folder.mkdir(parents=True, exist_ok=True)

    @property
    def all_center_points_file(self) -> Path:
        return self._all_center_points_file

    @all_center_points_file.setter
    def all_center_points_file(self, value: str | Path):
        self._all_center_points_file = self.output_folder.joinpath(value)

    @property
    def uncertainty_report_file(self) -> Path:
        """Sidecar JSON report for the optional nozzle-uncertainty bootstrap."""
        return self.output_folder / self.uncertainty_report_filename

    @property
    def n_distortion_coefs(self) -> int:
        """"""
        return self._n_distortion_coefs

    @n_distortion_coefs.setter
    def n_distortion_coefs(self, value: int):
        if value not in self.VALID_DISTORTION_COEFS:
            raise ValueError(f"n_distortion_coefs must be one of {self.VALID_DISTORTION_COEFS}, got {value}")

        self._n_distortion_coefs = int(value)

    @property
    def image_name_patterns(self) -> tuple[str, ...]:
        return self._image_name_patterns

    @image_name_patterns.setter
    def image_name_patterns(self, value: tuple[str, ...] | str):
        # Handle single string or tuple/list
        if isinstance(value, str):
            value = (value,)
        self._image_name_patterns = tuple(value)
