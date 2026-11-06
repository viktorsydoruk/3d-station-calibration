# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Command-line runner for the optional ZeroC Ice calibration server."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path
from typing import Any

from .. import __version__
from . import DEFAULT_MESSAGE_SIZE_MAX_KB

__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_IDENTITY",
    "DEFAULT_MESSAGE_SIZE_MAX_KB",
    "run_cli",
    "run_server",
]

DEFAULT_ENDPOINT = "tcp -h 127.0.0.1 -p 10000"
DEFAULT_IDENTITY = "CalibrationPhenoseederIcing"


def _install_shutdown_handlers(communicator: Any) -> dict[int, Any]:
    """Turn SIGINT/SIGTERM/SIGBREAK into a clean Ice communicator shutdown."""
    previous: dict[int, Any] = {}

    def request_shutdown(_signum: int, _frame: Any) -> None:
        communicator.shutdown()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        try:
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_shutdown)
        except (AttributeError, OSError, ValueError):
            previous.pop(signum, None)
    return previous


def _restore_shutdown_handlers(previous: dict[int, Any]) -> None:
    """Restore the handlers that were active before :func:`run_server`."""
    for signum, handler in previous.items():
        try:
            signal.signal(signum, handler)
        except (OSError, ValueError):
            continue


def run_server(config_file: str | Path,
               *,
               endpoint: str = DEFAULT_ENDPOINT,
               identity: str = DEFAULT_IDENTITY,
               message_size_max_kb: int = DEFAULT_MESSAGE_SIZE_MAX_KB) -> None:
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
    communicator = Ice.initialize([
        f"--Ice.MessageSizeMax={int(message_size_max_kb)}",
    ])
    shutdown_handlers: dict[int, Any] = {}
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
        shutdown_handlers = _install_shutdown_handlers(communicator)
        communicator.waitForShutdown()
    except KeyboardInterrupt:
        pass
    finally:
        _restore_shutdown_handlers(shutdown_handlers)
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
        "--message-size-max-kb",
        type=int,
        default=DEFAULT_MESSAGE_SIZE_MAX_KB,
        help=(
            "maximum incoming Ice message size in KiB "
            f"(default: {DEFAULT_MESSAGE_SIZE_MAX_KB})"
        ),
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
        message_size_max_kb=args.message_size_max_kb,
    )


if __name__ == "__main__":  # pragma: no cover
    run_cli()
