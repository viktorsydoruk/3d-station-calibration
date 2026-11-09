# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the folder-workflow command-line parser."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import station_calibration.cli as cli
from station_calibration import Settings


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


def test_run_cli_forwards_bootstrap_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "main",
        lambda folder, **opts: captured.update(folder=folder, opts=opts),
    )

    cli.run_cli(
        [
            str(tmp_path),
            "--bootstrap",
            "--bootstrap-n",
            "25",
            "--bootstrap-seed",
            "4",
        ]
    )

    assert captured["opts"] == {
        "uncertainty_enabled": True,
        "uncertainty_n_bootstrap": 25,
        "uncertainty_seed": 4,
    }


def test_run_cli_bootstrap_count_implies_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "main",
        lambda folder, **opts: captured.update(folder=folder, opts=opts),
    )

    cli.run_cli([str(tmp_path), "--bootstrap-n", "10"])

    assert captured["opts"] == {
        "uncertainty_enabled": True,
        "uncertainty_n_bootstrap": 10,
    }


def test_run_cli_can_disable_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "main",
        lambda folder, **opts: captured.update(folder=folder, opts=opts),
    )

    cli.run_cli([str(tmp_path), "--no-bootstrap"])

    assert captured["opts"] == {"uncertainty_enabled": False}


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


def test_write_nozzle_uncertainty_report_writes_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        tmp_path,
        uncertainty_enabled=True,
        uncertainty_n_bootstrap=7,
        uncertainty_seed=11,
    )
    result = SimpleNamespace(
        observation_count=12,
        n_used=10,
        rmse=0.5,
        n_distortion_coefs=0,
    )
    calls: list[dict[str, object]] = []

    def fake_bootstrap(observations, calibration_result, bootstrap_settings, *, n_bootstrap, seed):
        calls.append(
            {
                "n_bootstrap": n_bootstrap,
                "seed": seed,
                "settings": bootstrap_settings,
            }
        )
        return SimpleNamespace(
            std=np.array([0.01, 0.02, 0.03]),
            norm_std=0.0374,
            n_failed=1,
            n_requested=n_bootstrap,
            as_dict=lambda: {
                "mode": "residual",
                "std": [0.01, 0.02, 0.03],
            },
        )

    monkeypatch.setattr(cli, "bootstrap_nozzle_home", fake_bootstrap)

    report_path = cli._write_nozzle_uncertainty_report(
        settings,
        result,
        [],
        nozzle_home_position=np.array([1.0, 2.0, 3.0]),
        sphere_home_position=np.array([4.0, 5.0, 6.0]),
        sphere_diameter_mm=10.0,
    )

    assert report_path == settings.uncertainty_report_file
    assert calls == [
        {
            "n_bootstrap": 7,
            "seed": 11,
            "settings": settings,
        }
    ]
    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["diagnostic"] == "nozzle_home_residual_bootstrap"
    assert document["source"] == str(tmp_path)
    assert document["fit"] == {
        "observation_count": 12,
        "observations_used": 10,
        "rmse": 0.5,
        "n_distortion_coefs": 0,
    }
    assert document["bootstrap_config"] == {
        "n_bootstrap": 7,
        "seed": 11,
    }
    assert document["sphere_home_position"] == [4.0, 5.0, 6.0]
    assert document["sphere_diameter_mm"] == 10.0
    assert document["nozzle_home_position"] == [1.0, 2.0, 3.0]
    output = capsys.readouterr().out
    assert "Nozzle uncertainty" in output
    assert "1 of 7 nozzle uncertainty bootstrap replicates failed" in output


def test_write_nozzle_uncertainty_report_is_skipped_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = Settings(tmp_path)
    called: list[bool] = []

    def fake_bootstrap(*args, **kwargs):
        called.append(True)

    monkeypatch.setattr(cli, "bootstrap_nozzle_home", fake_bootstrap)
    result = SimpleNamespace(
        observation_count=12,
        n_used=10,
        rmse=0.5,
        n_distortion_coefs=0,
    )

    assert (
        cli._write_nozzle_uncertainty_report(
            settings,
            result,
            [],
            nozzle_home_position=np.array([1.0, 2.0, 3.0]),
            sphere_home_position=np.array([4.0, 5.0, 6.0]),
            sphere_diameter_mm=10.0,
        )
        is None
    )
    assert called == []


def test_write_nozzle_uncertainty_report_warns_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(tmp_path, uncertainty_enabled=True)
    result = SimpleNamespace(
        observation_count=12,
        n_used=10,
        rmse=0.5,
        n_distortion_coefs=0,
    )

    def failing_bootstrap(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(cli, "bootstrap_nozzle_home", failing_bootstrap)

    assert (
        cli._write_nozzle_uncertainty_report(
            settings,
            result,
            [],
            nozzle_home_position=np.array([1.0, 2.0, 3.0]),
            sphere_home_position=np.array([4.0, 5.0, 6.0]),
            sphere_diameter_mm=10.0,
        )
        is None
    )
    assert "nozzle uncertainty bootstrap failed: synthetic failure" in (
        capsys.readouterr().out
    )
