""" Here is the settings class for 3D station calibration software

    This class consists all the parameters needed to properly run all parts of calibration routine.
    It consists two groups of parameters: one group can be changed only through the config.ini file, when another
    though the keywords arguments given to the class during its initialization

    created 31.08.2026
"""


__all__ = ['Settings', 'PossibleOptions']

import tomllib
from pathlib import Path
from typing import TypedDict
from typing import Any


class PossibleOptions(TypedDict):
    """
        This is for type hint of opt. in Setting class to use type hint Unpack[PossibleOptions]
    """
    config: dict[str, Any]
    debug: bool
    store_debug_images: bool
    robot_pos_file: Path
    output_folder: Path
    debug_folder: Path
    all_center_points_file: Path
    load_stored_data: bool
    image_name_patterns: tuple[str, ...]
    sort_imagenames_by_mtime: bool

    bg_height_pxs: int
    bg_color_est_perc: float
    fixed_bg_threshold: float
    n_move_aver: int
    sphere_center_to_nozzle_part: float
    min_bg_pixels_on_edges: int
    blur_est_border_thickness: int
    fix_cx_cy: bool
    n_distortion_coefs: int
    n_iterations: int
    allowed_outliers: float


class Settings:
    """
        Settings class to configure 3D station calibration software
    """
    # Class-level defaults
    DEFAULT_CONFIG_PATH = Path(r"./_3dsc_resources/config.toml")
    VALID_DISTORTION_COEFS = (0, 4, 5, 8, 12, 14)

    config_file_path: Path
    config: dict[str, Any]
    _opts: dict[str, Any]
    debug: bool
    store_debug_images: bool
    _robot_pos_file: Path
    _all_center_points_file: Path
    _output_folder: Path
    _debug_folder: Path
    load_stored_data: bool
    _image_name_patterns: tuple[str, ...]
    sort_imagenames_by_mtime: bool

    bg_height_pxs: int
    bg_color_est_perc: float
    fixed_bg_threshold: float
    n_move_aver: int
    sphere_center_to_nozzle_part: float
    min_bg_pixels_on_edges: int
    blur_est_border_thickness: int
    fix_cx_cy: bool
    _n_distortion_coefs: int

    n_iterations: int
    allowed_outliers: float

    def __init__(self,
                 folder_to_analyze: str,
                 **opts: PossibleOptions
                 ):

        #
        # Defining all the parameters
        #
        self.main_folder = Path(folder_to_analyze)  # should be defined first
        self._opts = opts

        # Validate unknown keys
        unknown_keys = set(opts.keys()) - set(PossibleOptions.__annotations__.keys())
        if unknown_keys:
            raise ValueError(
                f"Unknown settings: {", ".join(sorted(unknown_keys))}"
            )

        # Load config file
        config_file_path = opts.get("config_file_path", self.DEFAULT_CONFIG_PATH)
        if not config_file_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file_path.absolute()}")

        with config_file_path.open('rb') as f:
            self.config = tomllib.load(f)

        # Initialize all settings (properties handle path transformations)

        self._init_general()  # should be always first initialized

        # general.files section
        self.robot_pos_file = self._get(self.config["general"]["files"], 'robot_pos_filename')
        self.output_folder = self._get(self.config["general"]["files"], 'output_folder')
        self.debug_folder = self._get(self.config["general"]["files"], 'debug_folder')
        self.all_center_points_file = self._get(self.config["general"]["files"], 'all_center_points_filename')
        self.image_names_patterns = self._get(self.config["general"]["files"], 'image_name_patterns')
        self.sort_imagenames_by_mtime = self._get(self.config["general"]["files"], 'sort_image_names_by_mtime')

        # analysis section
        self.n_iterations = self._get(self.config["analysis"], 'n_iterations')
        self.allowed_outliers = self._get(self.config["analysis"], 'max_outliers')

        # analysis.background section
        self.fixed_bg_threshold = self._get(self.config["analysis"]["background"], 'fixed_bg_threshold')
        self.bg_height_pxs = self._get(self.config["analysis"]["background"], 'bg_height_pxs')
        self.bg_color_est_perc = self._get(self.config["analysis"]["background"], 'bg_color_est_perc')

        # analysis.sphere_projection section
        self.n_move_aver = self._get(self.config["analysis"]["sphere_projection"], 'n_move_aver')
        self.sphere_center_to_nozzle_part = self._get(self.config["analysis"]["sphere_projection"], 'sphere_center_to_nozzle_part')
        self.min_bg_pixels_on_edges = self._get(self.config["analysis"]["sphere_projection"], 'min_bg_pixels_on_edges')
        self.blur_est_border_thickness = self._get(self.config["analysis"]["sphere_projection"], 'blur_est_border_thickness')

        # analysis.fit
        self.fix_cx_cy = self._get(self.config["analysis"]["fit"], 'fix_cx_cy')
        self.n_distortion_coefs = self._get(self.config["analysis"]["fit"], 'n_distortion_coefs')

    def _get(self,
             section: dict[str, Any],
             key: str,
             default: Any = None) -> Any:
        """
            Get value from section, optionally overridden by __init__ kwargs
        :param section: section read from toml file
        :param key: key to read value
        :param default: default value
        :return: value
        """
        # Check if there's a runtime override
        if key in self._opts:
            return self._opts[key]

        # Fall back to config file
        if default is not None:
            return section.get(key, default)
        return section[key]

    def _init_general(self) -> None:
        general = self.config["general"]
        self.debug = self._get(general, 'debug', False)
        self.store_debug_images = self._get(general, 'store_debug_images', False)
        self.load_stored_data = self._get(general, 'load_stored_data', False)

    def _init_files(self) -> None:
        files = self.config["general"]["files"]
        self._robot_pos_file = self._get(files, "robot_pos_filename")
        self._output_folder = self._get(files, "output_folder")
        self._debug_folder = self._get(files, "debug_folder")
        self._all_center_points_file = self._get(files, "all_center_points_filename")
        self._imagenames_patterns = self._get(files, "image_name_patterns", ('.tif',))
        self.sort_imagenames_by_mtime = self._get(files, "sort_image_names_by_mtime", False)

    def _init_analysis(self) -> None:
        analysis = self.config["analysis"]
        self.n_iterations = self._get(analysis, "n_iterations", 1)
        self.allowed_outliers = self._get(analysis, "max_outliers", 0)

    def _init_background(self) -> None:
        bg = self.config["analysis"]["background"]
        self.bg_height_pxs = self._get(bg, "bg_height_pxs")
        self.bg_color_est_perc = self._get(bg, "bg_color_est_perc")
        self.fixed_bg_threshold = self._get(bg, "fixed_bg_threshold")

    def _init_sphere_projection(self) -> None:
        sphere = self.config["analysis"]["sphere_projection"]
        self.n_move_aver = self._get(sphere, "n_move_aver")
        self.sphere_center_to_nozzle_part = self._get(sphere, "sphere_center_to_nozzle_part")
        self.min_bg_pixels_on_edges = self._get(sphere, "min_bg_pixels_on_edges")
        self.blur_est_border_thickness = self._get(sphere, "blur_est_border_thickness")

    def _init_fit(self) -> None:
        fit = self.config["analysis"]["fit"]
        self.fix_cx_cy = self._get(fit, "fix_cx_cy", True)
        self._n_distortion_coefs = self._get(fit, "n_distortion_coefs", 0)

    # -----------------------------------------------------------------
    # Properties with validation/transformation
    # -----------------------------------------------------------------

    @property
    def robot_pos_file(self) -> Path:
        return self._robot_pos_file

    @robot_pos_file.setter
    def robot_pos_file(self, value: str):
        self._robot_pos_file = self.main_folder.joinpath(value)

    @property
    def output_folder(self) -> Path:
        """"""
        return self._output_folder

    @output_folder.setter
    def output_folder(self, value: str):
        self._output_folder = self.main_folder.joinpath(value)
        self._output_folder.mkdir(parents=True, exist_ok=True)

    @property
    def debug_folder(self) -> Path:
        """"""
        return self._debug_folder

    @debug_folder.setter
    def debug_folder(self, value: str):
        if self.debug or self.store_debug_images:
            self._debug_folder = self.main_folder.joinpath(value)
            self._debug_folder.mkdir(parents=True, exist_ok=True)

    @property
    def all_center_points_file(self) -> Path:
        return self._all_center_points_file

    @all_center_points_file.setter
    def all_center_points_file(self, value: str):
        self._all_center_points_file = self.output_folder.joinpath(value)

    @property
    def n_distortion_coefs(self) -> int:
        """"""
        return self._n_distortion_coefs

    @n_distortion_coefs.setter
    def n_distortion_coefs(self, value: int):
        if value not in self.VALID_DISTORTION_COEFS:
            raise ValueError(f"n_distortion_coefs must be on of {self.VALID_DISTORTION_COEFS}, got {value}")

        self._n_distortion_coefs = value

    @property
    def image_name_patterns(self) -> tuple[str, ...]:
        return self._image_name_patterns

    @image_name_patterns.setter
    def image_name_patterns(self, value: tuple[str, ...] | str):
        # Handle single string or tuple
        if isinstance(value, str):
            value = (value,)
        self._image_name_patterns = value
