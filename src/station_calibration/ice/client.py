# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Convenience client for the optional ZeroC Ice calibration server."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np

from .. import __version__

from ._generated import ensure_generated_on_path

ensure_generated_on_path()

import Ice  # noqa: E402
from Phenoseeder import CalibrationPhenoseederIcingPrx, Point  # noqa: E402
from Phyto.Common import (  # noqa: E402
    IMAGEFORMAT,
    extrinsicParams,
    intrinsicParams,
)

from .images import decode_image, image_data_from_array  # noqa: E402

__all__ = [
    "DEFAULT_PROXY",
    "CalibrationIceClient",
    "run_cli",
]

DEFAULT_PROXY = "CalibrationPhenoseederIcing:tcp -h 127.0.0.1 -p 10000"


class CalibrationIceClient:
    """Thin synchronous client around ``CalibrationPhenoseederIcingPrx``."""

    def __init__(self,
                 proxy: CalibrationPhenoseederIcingPrx | Ice.ObjectPrx,
                 communicator: Ice.Communicator | None = None) -> None:
        if isinstance(proxy, CalibrationPhenoseederIcingPrx):
            self.proxy = proxy
        else:
            checked = CalibrationPhenoseederIcingPrx.uncheckedCast(proxy)
            if checked is None:
                raise TypeError("proxy does not implement CalibrationPhenoseederIcing")
            self.proxy = checked
        self._communicator = communicator

    @classmethod
    def connect(cls,
                proxy: str = DEFAULT_PROXY,
                *,
                ice_config: str | Path | None = None) -> "CalibrationIceClient":
        """Create a communicator and connect to an Ice calibration server."""
        init_args: list[str] = []
        if ice_config is not None:
            init_args.append(f"--Ice.Config={Path(ice_config).expanduser()}")
        communicator = Ice.initialize(init_args)
        try:
            base = communicator.stringToProxy(proxy)
            checked = CalibrationPhenoseederIcingPrx.checkedCast(base)
            if checked is None:
                raise RuntimeError(
                    f"Proxy does not implement CalibrationPhenoseederIcing: {proxy}"
                )
        except Exception:
            communicator.destroy()
            raise
        return cls(checked, communicator)

    def close(self) -> None:
        """Destroy the communicator owned by :meth:`connect`, if any."""
        if self._communicator is not None:
            self._communicator.destroy()
            self._communicator = None

    def __enter__(self) -> "CalibrationIceClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def init(self,
             procedure_id: int,
             configurationfilepath: str | Path | None = None) -> str:
        """Start a procedure session and return its remote date folder."""
        return self.proxy.init(
            int(procedure_id),
            (
                str(configurationfilepath)
                if configurationfilepath is not None
                else None
            ),
        )

    def add_image(self,
                  image: np.ndarray | bytes,
                  robot_coord: Iterable[float],
                  *,
                  imgformat: IMAGEFORMAT | None = None) -> None:
        """Send one raw camera frame and its robot coordinate.

        ``image`` may be a NumPy frame or encoded image bytes (TIFF, PNG, ...).
        Encoded bytes are decoded locally because the shared ``imageData``
        contract transports raw pixels.
        """
        array = decode_image(image) if isinstance(image, bytes) else image
        x, y, z = (float(value) for value in robot_coord)
        self.proxy.addData(
            Point(x=x, y=y, z=z),
            image_data_from_array(array, imgformat=imgformat),
        )

    def add_image_file(self,
                       image_path: str | Path,
                       robot_coord: Iterable[float],
                       *,
                       imgformat: IMAGEFORMAT | None = None) -> None:
        """Read an image file, decode it, and send the raw frame."""
        self.add_image(
            Path(image_path).read_bytes(),
            robot_coord,
            imgformat=imgformat,
        )

    def is_ready(self) -> bool:
        return bool(self.proxy.isReady())

    def abort(self) -> None:
        """Abort the active calibration and allow another procedure."""
        self.proxy.abort()

    def finish(self) -> bool:
        """Force the final fit and return whether a result is available."""
        return bool(self.proxy.finish())

    def get_intrinsic(self) -> tuple[intrinsicParams, list[float]]:
        return self.proxy.getIntrinsic()

    def get_extrinsic(self) -> tuple[extrinsicParams, list[float]]:
        return self.proxy.getExtrinsic()

    def get_distortion(self) -> tuple[list[float], list[float]]:
        return self.proxy.getDistortion()

    def get_optimal_nozzle_position(self) -> Point:
        return self.proxy.getOptimalNozzlePosition()


def run_cli(argv: list[str] | None = None) -> None:
    """Send one image to a running server and print the calibration state."""
    parser = argparse.ArgumentParser(
        prog="3dsc-ice-client",
        description="Send one image to a running calibration Ice server.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--proxy",
        default=DEFAULT_PROXY,
        help=f"Ice proxy (default: {DEFAULT_PROXY})",
    )
    parser.add_argument(
        "--procedure-id",
        type=int,
        required=True,
        help="procedure ID selecting <procedures-root>/<procedure-id>/config.toml",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "optional absolute server-side TOML configuration merged with the "
            "procedure default for this session"
        ),
    )
    parser.add_argument("image", type=Path, help="encoded image to send")
    parser.add_argument("--x", type=float, required=True, help="robot X coordinate")
    parser.add_argument("--y", type=float, required=True, help="robot Y coordinate")
    parser.add_argument("--z", type=float, required=True, help="robot Z coordinate")
    args = parser.parse_args(argv)

    with CalibrationIceClient.connect(args.proxy) as client:
        session_folder = client.init(args.procedure_id, args.config)
        print(f"session: {session_folder}")
        client.add_image_file(args.image, (args.x, args.y, args.z))
        ready = client.is_ready()
        print(f"ready: {ready}")
        if not ready:
            return

        intrinsic, intrinsic_error = client.get_intrinsic()
        extrinsic, extrinsic_error = client.get_extrinsic()
        distortion, distortion_error = client.get_distortion()
        nozzle = client.get_optimal_nozzle_position()
        intrinsic_matrix = np.asarray(intrinsic.modelParams, dtype=np.float64).reshape(3, 3)
        extrinsic_params = np.asarray(extrinsic.modelParams, dtype=np.float64)
        translation = extrinsic_params[:3]
        rotation = extrinsic_params[3:].reshape(3, 3)
        print(f"intrinsic:\n{intrinsic_matrix}")
        print(f"intrinsic error: {intrinsic_error}")
        print(f"rotation:\n{rotation}")
        print(f"translation: {translation}")
        print(f"extrinsic error: {extrinsic_error}")
        print(f"distortion: {distortion}")
        print(f"distortion error: {distortion_error}")
        print(f"nozzle: x={nozzle.x} y={nozzle.y} z={nozzle.z}")


if __name__ == "__main__":
    run_cli()
