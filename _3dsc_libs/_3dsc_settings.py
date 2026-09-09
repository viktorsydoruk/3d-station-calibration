""" Here is the settings class for 3D station calibration software

    This class consists all the parameters needed to properly run all parts of calibration routine.
    It consists two groups of parameters: one group can be changed only through the config.ini file, when another
    though the keywords arguments given to the class during its initialization

    created 31.08.2026
"""


__all__ = ['Settings', 'PossibleOptions']

import configparser
from pathlib import Path
from typing import TypedDict


class PossibleOptions(TypedDict):
    """
        This is for type hint of opt. in Setting class to use type hint Unpack[PossibleOptions]
    """
    config: configparser.ConfigParser
    debug: bool
    store_debug_images: bool
    robot_pos_file: Path
    output_folder: Path
    debug_folder: Path
    all_center_points_file: Path
    load_stored_data: bool
    imagenames_patterns: tuple[str, ...]
    sort_imagenames_by_mtime: bool

    bg_height_pxs: int
    bg_color_est_perc: float
    n_move_aver: int
    sphere_center_to_nozzle_part: float
    min_bg_pixels_on_edges: int
    blur_est_border_thickness: int
    fix_cx_cy: bool
    n_distribution_coefs: int
    n_iterations: int


class Settings:
    """
        Settings class to configure 3D station calibration software
    """
    config: configparser.ConfigParser
    debug: bool
    store_debug_images: bool
    __robot_pos_file: Path
    __all_center_points_file: Path
    __output_folder: Path
    __debug_folder: Path
    load_stored_data: bool
    __imagenames_patterns: tuple[str, ...]
    sort_imagenames_by_mtime: bool

    bg_height_pxs: int
    bg_color_est_perc: float
    n_move_aver: int
    sphere_center_to_nozzle_part: float
    min_bg_pixels_on_edges: int
    blur_est_border_thickness: int
    fix_cx_cy: bool
    __n_distribution_coefs: int

    n_iterations: int

    def __init__(self,
                 folder_to_analyze: str,
                 **opts):

        #
        # Defining all the parameters
        #
        self.main_folder = Path(folder_to_analyze)  # should be defined first

        for each_key in opts.keys():
            if each_key not in PossibleOptions.__annotations__.keys():
                print(f"IMPORTANT: {each_key} is not existing in settings")

        config_file_path = opts.get("config_file_path", Path(r"./_3dsc_resources/config.ini"))

        if not config_file_path.exists():
            raise Exception(f"config file doesn't exist {config_file_path.absolute()}")

        self.config = configparser.ConfigParser()
        self.config.read(config_file_path)

        # GENERAL section parameters
        # ___ should be first defined ___
        self.debug = opts.get('debug', self.config.getboolean("GENERAL", "Debug"))
        self.store_debug_images = opts.get('store_debug_images', self.config.getboolean("GENERAL", "StoreDebugImages"))
        self.output_folder = opts.get('output_folder', self.config["GENERAL"]["OutputFolder"])
        self.debug_folder = opts.get('debug_folder', self.config["GENERAL"]["DebugFolder"])
        # -------------------------------

        self.robot_pos_file = opts.get('robot_pos_filename', self.config["GENERAL"]["RobotPosFilename"])
        self.all_center_points_file = opts.get('all_center_points_filename', self.config["GENERAL"]["AllCenterPointsFilename"])
        self.load_stored_data = opts.get('load_stored_data', self.config.getboolean("GENERAL", "LoadStoredData"))
        self.imagenames_patterns = opts.get('imagenames_patterns', self.config["GENERAL"]["ImagenamesPatterns"])
        self.sort_imagenames_by_mtime = opts.get('sort_imagenames_by_mtime', self.config.getboolean("GENERAL", "SortImagenamesByMtime"))

        # ANALYSIS section parameters
        self.bg_height_pxs = opts.get('bg_height_pxs', self.config.getint("ANALYSIS", "BGHeightPxs"))
        self.bg_color_est_perc = opts.get('bg_color_est_perc', self.config.getfloat("ANALYSIS", "BGColorEstPerc"))
        self.n_move_aver = opts.get('n_move_aver', self.config.getint("ANALYSIS", "NMoveAver"))
        self.sphere_center_to_nozzle_part = opts.get('sphere_center_to_nozzle_part', self.config.getfloat("ANALYSIS", "SphereCenterToNozzlePart"))
        self.min_bg_pixels_on_edges = opts.get('min_bg_pixels_on_edges', self.config.getint("ANALYSIS", "MinBGPixelsOnEdges"))
        self.blur_est_border_thickness = opts.get('blur_est_border_thickness', self.config.getint("ANALYSIS", "BlurEstBorderThickness"))
        self.fix_cx_cy = opts.get('fix_cx_cy', self.config.getboolean("ANALYSIS", "FixCxCy"))
        self.n_distortion_coefs = opts.get('n_distortion_coefs', self.config.getint("ANALYSIS", "NDistortionCoefs"))
        self.n_iterations = opts.get('n_iterations', self.config.getint("ANALYSIS", "NIterations"))

    @property
    def robot_pos_file(self) -> Path:
        return self.__robot_pos_file

    @robot_pos_file.setter
    def robot_pos_file(self, value: str):
        self.__robot_pos_file = self.main_folder.joinpath(value)

    @property
    def output_folder(self) -> Path:
        """"""
        return self.__output_folder

    @output_folder.setter
    def output_folder(self, value: str):
        self.__output_folder = self.main_folder.joinpath(value)
        self.__output_folder.mkdir(exist_ok=True)

    @property
    def debug_folder(self) -> Path:
        """"""
        return self.__debug_folder

    @debug_folder.setter
    def debug_folder(self, value: str):
        if self.debug or self.store_debug_images:
            self.__debug_folder = self.main_folder.joinpath(value)
            self.__debug_folder.mkdir(exist_ok=True)

    @property
    def all_center_points_file(self) -> Path:
        return self.__all_center_points_file

    @all_center_points_file.setter
    def all_center_points_file(self, value: str):
        self.__all_center_points_file = self.output_folder.joinpath(value)

    @property
    def imagenames_patterns(self) -> tuple[str, ...]:
        """"""
        return self.__image_names_patterns

    @imagenames_patterns.setter
    def imagenames_patterns(self, values: str | tuple[str, ...]):
        if isinstance(values, str):
            try:
                values = tuple(p.strip() for p in values.split(","))
            except Exception as exc:
                print(f"{exc.__class__.__name__} happened by getting imagenames_patterns from config.ini: {exc}")
                values = ('',)

        self.__image_names_patterns = values


    @property
    def n_distortion_coefs(self) -> int:
        """"""
        return self.__n_distortion_coefs

    @n_distortion_coefs.setter
    def n_distortion_coefs(self, value: int):
        if value not in (0, 4, 5, 8, 12, 14):
            raise ValueError(f"n_distortion_coefs value {value} is not valid")

        self.__n_distortion_coefs = value