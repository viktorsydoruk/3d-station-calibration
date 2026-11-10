# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Folder-based source adapter for the shared calibration session."""

from __future__ import annotations

__all__ = [
    "FolderDataset",
    "FolderCalibrationSource",
    "create_folder_session",
    "observations_to_arrays",
]

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..debug import DebugInfo
from ..models import CalibrationObservation, ObservationRejection
from ..session import CalibrationSession
from ..settings import Settings
from ..storage import (
    load_all_points_with_covariances,
    load_robot_positions,
    search_images,
    store_all_points,
)
from ..vision import (
    analyze_images,
    filtering_data_by_radius,
    get_radius_outlier_mask,
)
from .base import ObservationDataset


@dataclass(frozen=True)
class FolderDataset(ObservationDataset):
    """
        Data loaded from one folder before it is fed into a calibration session.

        ``observations`` are all successfully extracted points. ``fit_observations``
        is the subset that should enter the fit; for freshly analyzed images this
        excludes radius outliers, while a stored point cache is already assumed to
        be filtered by the folder workflow.
    """

    observations: tuple[CalibrationObservation, ...]
    fit_observations: tuple[CalibrationObservation, ...]
    rejections: tuple[ObservationRejection, ...]
    image_size_xy: tuple[int, int]
    from_stored_data: bool

    @property
    def apply_radius_filter(self) -> bool:
        """Whether the session should apply radius filtering to these observations."""
        return not self.from_stored_data


def observations_to_arrays(
    observations: Sequence[CalibrationObservation],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert observations to the arrays used by the numerical pipeline."""
    if not observations:
        return (
            np.empty((0, 3), dtype=np.float64),
            np.empty((0, 2), dtype=np.float64),
            np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.int8),
        )

    robot_positions = np.array(
        [observation.robot_position for observation in observations], dtype=np.float64
    )
    center_points = np.array(
        [observation.image_center for observation in observations], dtype=np.float64
    )
    radii = np.array([observation.radius for observation in observations], dtype=np.float64)
    sigmas = np.array([observation.sigma for observation in observations], dtype=np.float64)
    directions = np.array(
        [observation.direction for observation in observations], dtype=np.int8
    )
    return robot_positions, center_points, radii, sigmas, directions


def _shape_from_row(image_size_row: np.ndarray) -> tuple[int, int] | None:
    row = np.asarray(image_size_row, dtype=np.float64)
    if row.shape != (2,) or not np.all(np.isfinite(row)):
        return None
    if row[0] <= 0 or row[1] <= 0:
        return None
    return int(row[0]), int(row[1])


def _image_size_xy(image_sizes: np.ndarray) -> tuple[int, int]:
    image_sizes = np.asarray(image_sizes, dtype=np.float64)
    if image_sizes.ndim != 2 or image_sizes.shape[1] != 2:
        raise ValueError(
            f"image_sizes must have shape (n, 2), got {image_sizes.shape}"
        )

    finite_rows = np.isfinite(image_sizes).all(axis=1)
    if not np.any(finite_rows):
        raise ValueError("Cannot determine image size without a valid image shape")

    height, width = np.nanmax(image_sizes[finite_rows], axis=0)
    return int(width), int(height)


def _valid_mask(
    robot_positions: np.ndarray,
    center_points: np.ndarray,
    radii: np.ndarray,
    sigmas: np.ndarray,
    image_sizes: np.ndarray,
    directions: np.ndarray,
) -> np.ndarray:
    finite = (
        np.isfinite(robot_positions).all(axis=1)
        & np.isfinite(center_points).all(axis=1)
        & np.isfinite(radii)
        & np.isfinite(sigmas)
        & (radii > 0)
        & (sigmas >= 0)
    )
    valid_shapes = np.array(
        [_shape_from_row(row) is not None for row in image_sizes], dtype=bool
    )
    valid_directions = np.isin(directions, (-1, 1))
    return finite & valid_shapes & valid_directions


def _make_observation(
    robot_position: np.ndarray,
    image_center: np.ndarray,
    radius: float,
    sigma: float,
    direction: int,
    image_shape: tuple[int, int],
    source: str | None,
    center_covariance: np.ndarray | None = None,
    binary_radius: float | None = None,
) -> CalibrationObservation:
    return CalibrationObservation(
        robot_position=robot_position,
        image_center=image_center,
        radius=radius,
        sigma=sigma,
        direction=direction,
        image_shape=image_shape,
        source=source,
        center_covariance=center_covariance,
        binary_radius=binary_radius,
    )


def _make_rejection(
    reason: str,
    direction: int,
    image_shape: tuple[int, int] | None,
    source: str | None,
) -> ObservationRejection:
    return ObservationRejection(
        reason=reason,
        direction=direction,
        image_shape=image_shape,
        source=source,
    )


def _observations_from_rows(
    robot_positions: np.ndarray,
    center_points: np.ndarray,
    radii: np.ndarray,
    sigmas: np.ndarray,
    directions: np.ndarray,
    image_sizes: np.ndarray,
    valid_mask: np.ndarray,
    source_names: Sequence[str] | None = None,
    center_covariances: np.ndarray | None = None,
    binary_radii: np.ndarray | None = None,
) -> tuple[CalibrationObservation, ...]:
    observations = []
    for index in np.flatnonzero(valid_mask):
        image_shape = _shape_from_row(image_sizes[index])
        if image_shape is None:
            continue
        source = source_names[int(index)] if source_names is not None else None
        covariance = None
        if (
            center_covariances is not None
            and np.all(np.isfinite(center_covariances[index]))
        ):
            covariance = center_covariances[index]
        binary_radius = None
        if binary_radii is not None and np.isfinite(binary_radii[index]):
            binary_radius = float(binary_radii[index])
        observations.append(
            _make_observation(
                robot_position=robot_positions[index],
                image_center=center_points[index],
                radius=float(radii[index]),
                sigma=float(sigmas[index]),
                direction=int(directions[index]),
                image_shape=image_shape,
                source=source,
                center_covariance=covariance,
                binary_radius=binary_radius,
            )
        )
    return tuple(observations)


def _without_radius_outliers(
    observations: tuple[CalibrationObservation, ...],
    radii: np.ndarray,
    sigmas: np.ndarray,
) -> tuple[CalibrationObservation, ...]:
    if not observations:
        return ()

    reference_radii = np.asarray(
        [
            observation.binary_radius
            if observation.binary_radius is not None
            else observation.radius
            for observation in observations
        ],
        dtype=np.float64,
    )
    outlier_mask = get_radius_outlier_mask(
        np.asarray(radii, dtype=np.float64),
        np.asarray(sigmas, dtype=np.float64),
        reference_radii,
    )
    return tuple(
        observation
        for observation, is_outlier in zip(observations, outlier_mask)
        if not is_outlier
    )


class FolderCalibrationSource:
    """Load one calibration folder as session observations."""

    def __init__(self,
                 settings: Settings,
                 print_debug: DebugInfo | None = None) -> None:
        self.settings = settings
        self.print_debug = (
            print_debug if print_debug is not None else DebugInfo(settings.debug)
        )

    def load(self) -> FolderDataset:
        """Load a stored point cache or analyze the folder images."""
        if (
            self.settings.load_stored_data
            and self.settings.all_center_points_file.exists()
        ):
            return self._load_stored()
        return self._analyze_images()

    def open_session(self, *, fit_every_n: int | None = None) -> CalibrationSession:
        """
            Load the folder and feed all observations into a calibration session.

            Folder mode normally uses ``fit_every_n=None`` and calls ``finish()`` once
            after loading; the Ice adapter can use the same session with incremental
            fits instead.
        """
        dataset = self.load()
        session = CalibrationSession(
            self.settings,
            self.print_debug,
            fit_every_n=fit_every_n,
            apply_radius_filter=dataset.apply_radius_filter,
        )
        for rejection in dataset.rejections:
            session.add_rejection(rejection)
        for observation in dataset.observations:
            session.add_observation(observation)
        return session

    def _load_stored(self) -> FolderDataset:
        point_file = self.settings.all_center_points_file
        (
            robot_positions,
            center_points,
            radii,
            sigmas,
            image_sizes,
            directions,
            center_covariances,
        ) = load_all_points_with_covariances(point_file)

        valid_mask = _valid_mask(
            robot_positions,
            center_points,
            radii,
            sigmas,
            image_sizes,
            directions,
        )
        observations = _observations_from_rows(
            robot_positions,
            center_points,
            radii,
            sigmas,
            directions,
            image_sizes,
            valid_mask,
            source_names=[str(point_file)] * len(robot_positions),
            center_covariances=center_covariances,
        )

        rejections = []
        for index in np.flatnonzero(~valid_mask):
            rejections.append(
                _make_rejection(
                    reason="stored point is invalid",
                    direction=int(directions[index]),
                    image_shape=_shape_from_row(image_sizes[index]),
                    source=str(point_file),
                )
            )

        return FolderDataset(
            observations=observations,
            fit_observations=observations,
            rejections=tuple(rejections),
            image_size_xy=_image_size_xy(image_sizes),
            from_stored_data=True,
        )

    def _analyze_images(self) -> FolderDataset:
        robot_positions, image_names = load_robot_positions(
            self.settings.robot_pos_file
        )
        self.print_debug(
            len(robot_positions), "robot position coordinates are collected"
        )

        image_filenames = search_images(
            self.settings.main_folder,
            image_names,
            patterns=self.settings.image_name_patterns,
            sort_by_mtime=self.settings.sort_imagenames_by_mtime,
        )
        self.print_debug(len(image_filenames), "images are found")

        if len(robot_positions) != len(image_filenames):
            raise ValueError(
                "The number of robot positions does not match the number of images: "
                f"{len(robot_positions)} vs {len(image_filenames)}"
            )

        analyses = analyze_images(
            image_filenames,
            bg_height_px=self.settings.bg_height_pxs,
            bg_color_est_perc=self.settings.bg_color_est_perc,
            bg_threshold_method=self.settings.bg_threshold_method,
            bg_noise_sigma=self.settings.bg_noise_sigma,
            fixed_bg_threshold=self.settings.fixed_bg_threshold,
            n_mov_aver=self.settings.n_move_aver,
            sphere_center_to_nozzle_part=self.settings.sphere_center_to_nozzle_part,
            min_bg_pixels_on_edges=self.settings.min_bg_pixels_on_edges,
            blur_est_border_thickness=self.settings.blur_est_border_thickness,
            subpixel_edges=self.settings.subpixel_edges,
            print_debug=self.print_debug,
            debug_folder=self.settings.debug_folder,
            store_debug_images=self.settings.store_debug_images,
        )

        n_images = len(analyses)
        center_points = np.full((n_images, 2), np.nan, dtype=np.float64)
        radii = np.full(n_images, np.nan, dtype=np.float64)
        sigmas = np.full(n_images, np.nan, dtype=np.float64)
        center_covariances = np.full((n_images, 2, 2), np.nan, dtype=np.float64)
        binary_radii = np.full(n_images, np.nan, dtype=np.float64)
        image_sizes = np.empty((n_images, 2), dtype=np.float64)
        directions = np.empty(n_images, dtype=np.int8)

        for index, analysis in enumerate(analyses):
            image_sizes[index] = analysis.image_shape
            directions[index] = analysis.direction
            if analysis.observation is not None:
                center_points[index] = [analysis.observation.x, analysis.observation.y]
                radii[index] = analysis.observation.radius
                sigmas[index] = analysis.observation.sigma
                if analysis.observation.center_covariance is not None:
                    center_covariances[index] = (
                        analysis.observation.center_covariance
                    )
                if analysis.observation.binary_radius is not None:
                    binary_radii[index] = analysis.observation.binary_radius

        # Preserve the folder cache: radius outliers are stored as NaN, even though
        # the session receives the raw observations and applies the same filter.
        storage_radii = radii.copy()
        storage_sigmas = sigmas.copy()
        filtering_data_by_radius(
            image_filenames,
            center_points,
            storage_sigmas,
            storage_radii,
            print_debug=self.print_debug,
            debug_folder=self.settings.debug_folder,
            reference_radii=binary_radii,
        )
        store_all_points(
            self.settings.all_center_points_file,
            robot_positions,
            center_points,
            storage_radii,
            storage_sigmas,
            image_sizes,
            directions,
            center_covariances,
        )

        valid_mask = _valid_mask(
            robot_positions,
            center_points,
            radii,
            sigmas,
            image_sizes,
            directions,
        )
        observations = _observations_from_rows(
            robot_positions,
            center_points,
            radii,
            sigmas,
            directions,
            image_sizes,
            valid_mask,
            source_names=[str(filename) for filename in image_filenames],
            center_covariances=center_covariances,
            binary_radii=binary_radii,
        )
        fit_observations = _without_radius_outliers(
            observations,
            radii[valid_mask],
            sigmas[valid_mask],
        )

        rejections = []
        for index, analysis in enumerate(analyses):
            if analysis.observation is None:
                rejections.append(
                    _make_rejection(
                        reason=analysis.reason or "image analysis failed",
                        direction=analysis.direction,
                        image_shape=analysis.image_shape,
                        source=str(image_filenames[index]),
                    )
                )
            elif not valid_mask[index]:
                rejections.append(
                    _make_rejection(
                        reason="invalid image analysis result",
                        direction=analysis.direction,
                        image_shape=analysis.image_shape,
                        source=str(image_filenames[index]),
                    )
                )

        return FolderDataset(
            observations=observations,
            fit_observations=fit_observations,
            rejections=tuple(rejections),
            image_size_xy=_image_size_xy(image_sizes),
            from_stored_data=False,
        )


def create_folder_session(
    settings: Settings,
    print_debug: DebugInfo | None = None,
    *,
    fit_every_n: int | None = None,
) -> CalibrationSession:
    """Load a folder and return a session ready for a final fit."""
    return FolderCalibrationSource(settings, print_debug).open_session(
        fit_every_n=fit_every_n
    )
