# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Station-profile resolution for the Ice server.

A deployment can keep several station profiles below one root. A station ID is
resolved to ``<root>/<station-id>/config.toml`` and
``<root>/<station-id>/data``. The Ice ``init`` operation can then accept the
station ID without exposing server-side paths to the client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "StationProfile",
    "StationRegistry",
]

_STATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class StationProfile:
    """Paths belonging to one station deployment profile."""

    station_id: str
    config_file: Path
    working_folder: Path


class StationRegistry:
    """Resolve station IDs below a deployment-owned station root."""

    def __init__(self, root: str | Path | None) -> None:
        self.root = (
            Path(root).expanduser().resolve()
            if root is not None
            else None
        )

    def resolve(self, station_id: str) -> StationProfile:
        """Return the profile for ``station_id``.

        Station IDs must start with a letter or digit and are otherwise
        restricted to letters, digits, ``_``, and ``-``. This prevents a client
        from using an ID to escape the configured station root.
        """
        if self.root is None:
            raise ValueError(
                "station IDs are not enabled; start the server with "
                "--stations-root"
            )
        if not _STATION_ID_RE.fullmatch(station_id):
            raise ValueError(
                f"invalid station ID {station_id!r}; start with a letter or "
                "digit and use only letters, digits, '_' or '-'"
            )

        station_dir = self.root / station_id
        config_file = station_dir / "config.toml"
        if not config_file.is_file():
            raise FileNotFoundError(
                f"station {station_id!r} has no configuration file: "
                f"{config_file}"
            )

        working_folder = station_dir / "data"
        working_folder.mkdir(parents=True, exist_ok=True)
        return StationProfile(
            station_id=station_id,
            config_file=config_file,
            working_folder=working_folder,
        )
