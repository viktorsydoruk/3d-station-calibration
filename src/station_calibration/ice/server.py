# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Command-line runner for the optional ZeroC Ice calibration server."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import __version__

__all__ = ["DEFAULT_ENDPOINT", "DEFAULT_IDENTITY", "run_cli", "run_server"]

DEFAULT_ENDPOINT = "tcp -h 127.0.0.1 -p 10000"
DEFAULT_IDENTITY = "CalibrationPhenoseederIcing"


def run_server(folder: str | Path,
               *,
               config_file: str | Path | None = None,
               stations_root: str | Path | None = None,
               endpoint: str = DEFAULT_ENDPOINT,
               identity: str = DEFAULT_IDENTITY) -> None:
    """Create the Ice adapter and block until it shuts down.

    The default folder is a server deployment setting: it is deliberately not
    part of the shared wire contract. Clients may still pass a different folder,
    a TOML path, or a station ID to the existing ``init`` operation. Station IDs
    are resolved below ``stations_root``.
    """
    try:
        import Ice
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit(
            "ZeroC Ice is not installed. Install the optional extra with: "
            "python -m pip install -e \".[ice]\""
        ) from exc

    from .adapter import CalibrationIceServant

    servant = CalibrationIceServant(
        folder,
        config_file=config_file,
        stations_root=stations_root,
    )
    communicator = Ice.initialize([])
    try:
        adapter = communicator.createObjectAdapterWithEndpoints(
            "CalibrationAdapter",
            endpoint,
        )
        proxy = adapter.add(
            servant,
            Ice.stringToIdentity(identity),
        )
        adapter.activate()
        print(f"Version: {__version__}", flush=True)
        print(f"Ice calibration server listening on {endpoint}", flush=True)
        if stations_root is not None:
            root = Path(stations_root).expanduser().resolve()
            print(f"Station profiles: {root}", flush=True)
        print(f"Proxy: {proxy.ice_toString()}", flush=True)
        communicator.waitForShutdown()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            servant.close()
        finally:
            communicator.destroy()


def run_cli(argv: list[str] | None = None) -> None:
    """Parse command-line arguments and start the server."""
    parser = argparse.ArgumentParser(
        prog="3dsc-ice-server",
        description="Serve the calibration session over ZeroC Ice.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "folder",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "default working folder used when init does not select a station "
            "profile; defaults to <stations-root>/default when omitted"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="optional TOML configuration; defaults to the packaged config",
    )
    parser.add_argument(
        "--stations-root",
        type=Path,
        default=None,
        help=(
            "root for station profiles; enables init(\"station-id\") using "
            "<root>/<id>/config.toml and <root>/<id>/data"
        ),
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Ice endpoint string (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--identity",
        default=DEFAULT_IDENTITY,
        help=f"Ice object identity (default: {DEFAULT_IDENTITY})",
    )
    args = parser.parse_args(argv)

    folder = args.folder
    if folder is None:
        if args.stations_root is None:
            parser.error("folder is required unless --stations-root is supplied")
        folder = args.stations_root / "default"

    run_server(
        folder,
        config_file=args.config,
        stations_root=args.stations_root,
        endpoint=args.endpoint,
        identity=args.identity,
    )


if __name__ == "__main__":
    run_cli()
