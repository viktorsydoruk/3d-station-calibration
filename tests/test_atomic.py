# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for crash-safe file replacement."""

from __future__ import annotations

from pathlib import Path

import pytest

import station_calibration.atomic as atomic_module
from station_calibration.atomic import atomic_write_text


def test_atomic_write_text_replaces_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "result.yaml"
    path.parent.mkdir()
    path.write_text("old\n", encoding="utf-8")

    atomic_write_text(path, "new\n")

    assert path.read_text(encoding="utf-8") == "new\n"
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_write_text_keeps_original_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "result.yaml"
    path.write_text("old\n", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(atomic_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(path, "new\n")

    assert path.read_text(encoding="utf-8") == "old\n"
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))
