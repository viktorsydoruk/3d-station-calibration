# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Compatibility checks for the migration from ``_3dsc_libs``."""

from __future__ import annotations


def test_legacy_package_reexports_public_api() -> None:
    import _3dsc_libs
    import _3dsc_libs._3dsc_folder as legacy_folder
    import _3dsc_libs._3dsc_session as legacy_session

    from station_calibration import (
        CalibrationSession,
        FolderCalibrationSource,
        Settings,
    )

    assert _3dsc_libs.CalibrationSession is CalibrationSession
    assert legacy_session.CalibrationSession is CalibrationSession
    assert legacy_folder.FolderCalibrationSource is FolderCalibrationSource
    assert _3dsc_libs.Settings is Settings


def test_default_configuration_lives_inside_the_package() -> None:
    from station_calibration import Settings

    config_file = Settings.DEFAULT_CONFIG_FILE
    assert config_file.is_absolute()
    assert config_file.is_file()
    assert config_file.parent.name == "resources"
