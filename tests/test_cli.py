# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the folder-workflow command-line parser."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

import station_calibration.cli as cli


def test_run_cli_forwards_parsed_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_main(folder: Path, **opts: object) -> None:
        captured["folder"] = folder
        captured["opts"] = opts

    monkeypatch.setattr(cli, "main", fake_main)

    cli.run_cli(
        [
            str(tmp_path),
            "--config",
            "config.toml",
            "--debug",
            "--store-debug-images",
            "--no-load-stored-data",
            "--target-observations",
            "100",
            "--max-observations",
            "200",
        ]
    )

    assert captured["folder"] == tmp_path
    assert captured["opts"] == {
        "config_file": Path("config.toml"),
        "debug": True,
        "store_debug_images": True,
        "load_stored_data": False,
        "target_observations": 100,
        "max_observations": 200,
    }


def test_run_cli_omits_unspecified_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "main",
        lambda folder, **opts: captured.update(folder=folder, opts=opts),
    )

    cli.run_cli([str(tmp_path)])

    assert captured["folder"] == tmp_path
    assert captured["opts"] == {}


def test_main_reports_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class InterruptSource:
        def __init__(self, settings, print_debug) -> None:
            pass

        def load(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "FolderCalibrationSource", InterruptSource)

    with pytest.raises(KeyboardInterrupt):
        cli.main(tmp_path, debug=True)

    assert "Interrupted by user" in capsys.readouterr().out


def test_module_entry_point_calls_run_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[bool] = []
    monkeypatch.setattr(cli, "run_cli", lambda: called.append(True))
    monkeypatch.setattr(sys, "argv", ["3dsc"])

    runpy.run_module("station_calibration", run_name="__main__")

    assert called == [True]
