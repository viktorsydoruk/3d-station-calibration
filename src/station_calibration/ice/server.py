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


def run_server(config_file: str | Path,
               *,
               endpoint: str = DEFAULT_ENDPOINT,
               identity: str = DEFAULT_IDENTITY) -> None:
    """Create the Ice adapter and block until it shuts down.

    ``config_file`` is the deployment config. It must contain
    ``[general] procedures_root`` pointing to the absolute folder that holds the
    per-procedure folders. The procedure default configurations live beside the
    procedure data, so the server does not need a separate default folder.
    """
    try:
        import Ice
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit(
            "ZeroC Ice is not installed. Install the optional extra with: "
            "python -m pip install -e \".[ice]\""
        ) from exc

    from ._generated import ensure_generated_on_path

    ensure_generated_on_path()

    from .adapter import CalibrationIceServant
    from .procedures import load_procedures_root

    procedures_root = load_procedures_root(config_file)
    servant = CalibrationIceServant(procedures_root)
    communicator = Ice.initialize([])
    try:
        adapter = communicator.createObjectAdapterWithEndpoints(
            "Calibration",
            endpoint,
        )
        adapter.add(servant, Ice.stringToIdentity(identity))
        adapter.activate()
        print(f"3D station calibration Ice server {__version__}", flush=True)
        print(f"Endpoint: {endpoint}", flush=True)
        print(f"Identity: {identity}", flush=True)
        print(f"Procedures root: {procedures_root}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        communicator.waitForShutdown()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            servant.close()
        finally:
            communicator.destroy()


def run_cli(argv: list[str] | None = None) -> None:
    """Run the command-line server entry point."""
    parser = argparse.ArgumentParser(
        prog="3dsc-ice-server",
        description=(
            "Serve the 3D station calibration interface over ZeroC Ice. "
            "All deployment paths come from the required TOML config."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help=(
            "server TOML config containing [general] procedures_root "
            "(absolute path)"
        ),
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Ice endpoint (default: {DEFAULT_ENDPOINT!r})",
    )
    parser.add_argument(
        "--identity",
        default=DEFAULT_IDENTITY,
        help=f"Ice identity (default: {DEFAULT_IDENTITY!r})",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args(argv)
    run_server(
        args.config,
        endpoint=args.endpoint,
        identity=args.identity,
    )


if __name__ == "__main__":  # pragma: no cover
    run_cli()
