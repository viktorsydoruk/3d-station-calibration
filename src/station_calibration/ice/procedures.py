# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Procedure-session layout and configuration merging for the Ice server.

The server owns a procedures root. Each procedure has a default
``config.toml`` and receives one timestamped folder per calibration:

``<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/config.toml``
``<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/data/``

If a procedure has not been used before, ``init`` creates its folder and copies
the packaged default configuration there. An optional absolute override file is
merged over that new procedure default. For an existing procedure the override
applies only to the current session.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..settings import Settings

__all__ = [
    "ProcedureRegistry",
    "ProcedureSession",
    "deep_merge",
    "dumps_toml",
    "load_procedures_root",
]

CONFIG_FILENAME = "config.toml"
DATA_DIRNAME = "data"
_DATE_FORMAT = "%Y%m%d_%H%M"

_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class ProcedureSession:
    """Paths belonging to one procedure calibration session."""

    procedure_id: int
    procedures_root: Path
    procedure_dir: Path
    session_dir: Path
    config_file: Path
    data_dir: Path
    default_config_file: Path
    override_config_file: Path | None


def load_procedures_root(config_file: str | Path) -> Path:
    """Read and validate ``[general] procedures_root`` from the server config."""
    path = Path(config_file).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"server config file not found: {path}")
    with path.open("rb") as handle:
        config = tomllib.load(handle)

    general = config.get("general")
    if not isinstance(general, dict):
        raise KeyError(f"missing config section '[general]' in {path}")
    raw_root = general.get("procedures_root")
    if raw_root is None:
        raise KeyError(
            f"missing required setting 'procedures_root' in [general] of {path}"
        )
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ValueError(
            f"'procedures_root' in {path} must be a non-empty absolute path"
        )

    root = Path(raw_root).expanduser()
    if not root.is_absolute():
        raise ValueError(
            f"'procedures_root' in {path} must be an absolute path: {raw_root!r}"
        )
    if not root.is_dir():
        raise FileNotFoundError(f"procedures root does not exist: {root}")
    return root.resolve()


class ProcedureRegistry:
    """Create timestamped sessions below a deployment-owned procedures root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError(f"procedures root must be an absolute path: {root!r}")
        self.root = self.root.resolve()

    def create_session(self,
                       procedure_id: int,
                       configuration_file: str | Path | None = None,
                       *,
                       now: datetime | None = None) -> ProcedureSession:
        """Create a new procedure session and write its merged configuration."""
        if isinstance(procedure_id, bool) or not isinstance(procedure_id, int):
            raise TypeError("procedureId must be an integer")
        procedure_dir = self.root / str(procedure_id)

        override_config: Path | None = None
        override_data: dict[str, Any] | None = None
        if configuration_file is not None:
            override_config = Path(configuration_file).expanduser()
            if not override_config.is_absolute():
                raise ValueError(
                    "configurationfilepath must be an absolute path: "
                    f"{configuration_file!r}"
                )
            if not override_config.is_file():
                raise FileNotFoundError(
                    f"configuration override file not found: {override_config}"
                )
            override_data = _load_toml(override_config)

        try:
            procedure_dir.mkdir(parents=True, exist_ok=True)
        except FileExistsError as exc:
            raise NotADirectoryError(
                f"procedure path is not a directory: {procedure_dir}"
            ) from exc

        default_config = procedure_dir / CONFIG_FILENAME
        procedure_config = _ensure_procedure_config(
            procedure_id,
            default_config,
            override_data,
        )
        merged_config = (
            deep_merge(procedure_config, override_data)
            if override_data is not None
            else deepcopy(procedure_config)
        )

        session_dir = self._create_session_dir(
            procedure_dir,
            now or datetime.now(),
        )
        try:
            data_dir = session_dir / DATA_DIRNAME
            data_dir.mkdir()
            config_file = session_dir / CONFIG_FILENAME
            config_file.write_text(
                dumps_toml(
                    merged_config,
                    header=(
                        f"Generated for procedure {procedure_id} on "
                        f"{session_dir.name}"
                    ),
                ),
                encoding="utf-8",
                newline="\n",
            )
        except Exception:
            shutil.rmtree(session_dir, ignore_errors=True)
            raise

        return ProcedureSession(
            procedure_id=procedure_id,
            procedures_root=self.root,
            procedure_dir=procedure_dir,
            session_dir=session_dir,
            config_file=config_file,
            data_dir=data_dir,
            default_config_file=default_config,
            override_config_file=override_config,
        )

    @staticmethod
    def _create_session_dir(parent: Path, now: datetime) -> Path:
        base_name = now.strftime(_DATE_FORMAT)
        suffix = 0
        while True:
            name = base_name if suffix == 0 else f"{base_name}_{suffix:02d}"
            candidate = parent / name
            try:
                candidate.mkdir()
            except FileExistsError:
                suffix += 1
                continue
            return candidate


def _ensure_procedure_config(procedure_id: int,
                             config_path: Path,
                             override: dict[str, Any] | None) -> dict[str, Any]:
    """Create a missing procedure config and return its effective contents.

    When no override is supplied, the packaged file is copied byte-for-byte so
    its comments stay intact. With an override, the merged configuration is
    written as normalized TOML. If another process creates the file first, that
    file wins and is loaded instead.
    """
    if config_path.is_file():
        return _load_toml(config_path)
    if config_path.exists():
        raise IsADirectoryError(
            f"procedure configuration path is not a file: {config_path}"
        )

    template_path = Settings.DEFAULT_CONFIG_FILE
    template = _load_toml(template_path)
    if override is None:
        procedure_config = template
        content = template_path.read_bytes()
    else:
        procedure_config = deep_merge(template, override)
        content = dumps_toml(
            procedure_config,
            header=(
                f"Procedure {procedure_id} created from the packaged default "
                "with an init override"
            ),
        ).encode("utf-8")

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
    )
    try:
        descriptor = os.open(config_path, flags, 0o644)
    except FileExistsError:
        return _load_toml(config_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    except Exception:
        try:
            config_path.unlink()
        except OSError:
            pass
        raise
    return procedure_config


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base``.

    Tables are merged recursively. Scalars and arrays from ``override`` replace
    the corresponding value in ``base``.
    """
    result = deepcopy(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            result[key] = deep_merge(current, value)
        else:
            result[key] = deepcopy(value)
    return result


def dumps_toml(data: dict[str, Any], *, header: str | None = None) -> str:
    """Serialize a TOML-compatible mapping.

    The project only needs to write configuration trees built from TOML scalar
    values, arrays, and nested tables, so this intentionally implements a small
    subset rather than adding a runtime TOML writer dependency.
    """
    lines: list[str] = []
    if header:
        lines.extend(f"# {line}" for line in header.splitlines())
    _write_table(data, [], lines)
    return "\n".join(lines).rstrip() + "\n"


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _write_table(table: dict[str, Any],
                 path: list[str],
                 lines: list[str]) -> None:
    scalars: list[tuple[str, Any]] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            scalars.append((key, value))

    if path:
        if lines:
            lines.append("")
        lines.append(f"[{_format_key_path(path)}]")

    for key, value in scalars:
        lines.append(f"{_format_key(key)} = {_format_value(value)}")
    for key, value in tables:
        _write_table(value, [*path, key], lines)


def _format_key_path(path: list[str]) -> str:
    return ".".join(_format_key(part) for part in path)


def _format_key(key: str) -> str:
    if _BARE_KEY_RE.fullmatch(key):
        return key
    return json.dumps(key, ensure_ascii=False)


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"unsupported TOML float value: {value!r}")
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    if value is None:
        raise ValueError("TOML does not support null values")
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")
