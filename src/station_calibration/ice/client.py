# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Convenience client for the optional ZeroC Ice calibration server."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from ._generated import ensure_generated_on_path

ensure_generated_on_path()

import Ice  # noqa: E402
from Phenoseeder import CalibrationPhenoseederIcingPrx, Point  # noqa: E402
from Phyto.Common import extrinsicParams, imageData, intrinsicParams  # noqa: E402

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

    def init(self, configurationfilepath: str | Path | None = None) -> None:
        """Initialize the remote session from a config file or folder path."""
        self.proxy.init(
            str(Path(configurationfilepath).expanduser())
            if configurationfilepath is not None
            else None
        )

    def add_image(self,
                  image_bytes: bytes,
                  robot_coord: Iterable[float],
                  *,
                  width: int = 0,
                  height: int = 0,
                  channels: int = 0) -> None:
        """Send one encoded image and its robot coordinate."""
        x, y, z = (float(value) for value in robot_coord)
        self.proxy.addData(
            Point(x=x, y=y, z=z),
            imageData(
                data=bytes(image_bytes),
                width=int(width),
                height=int(height),
                channels=int(channels),
            ),
        )

    def add_image_file(self,
                       image_path: str | Path,
                       robot_coord: Iterable[float]) -> None:
        """Read an image file, derive its dimensions, and send it."""
        data = Path(image_path).read_bytes()
        decoded = cv2.imdecode(
            np.frombuffer(data, dtype=np.uint8),
            cv2.IMREAD_UNCHANGED,
        )
        if decoded is None:
            width = height = channels = 0
        else:
            height, width = decoded.shape[:2]
            channels = 1 if decoded.ndim == 2 else decoded.shape[2]
        self.add_image(
            data,
            robot_coord,
            width=width,
            height=height,
            channels=channels,
        )

    def is_ready(self) -> bool:
        return bool(self.proxy.isReady())

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
        "--proxy",
        default=DEFAULT_PROXY,
        help=f"Ice proxy (default: {DEFAULT_PROXY})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="optional TOML configuration or calibration folder for init()",
    )
    parser.add_argument("image", type=Path, help="encoded image to send")
    parser.add_argument("--x", type=float, required=True, help="robot X coordinate")
    parser.add_argument("--y", type=float, required=True, help="robot Y coordinate")
    parser.add_argument("--z", type=float, required=True, help="robot Z coordinate")
    args = parser.parse_args(argv)

    with CalibrationIceClient.connect(args.proxy) as client:
        client.init(args.config)
        client.add_image_file(args.image, (args.x, args.y, args.z))
        ready = client.is_ready()
        print(f"ready: {ready}")
        if not ready:
            return

        intrinsic, intrinsic_error = client.get_intrinsic()
        extrinsic, extrinsic_error = client.get_extrinsic()
        distortion, distortion_error = client.get_distortion()
        nozzle = client.get_optimal_nozzle_position()
        intrinsic_matrix = np.asarray(intrinsic.matrix, dtype=np.float64).reshape(3, 3)
        print(f"intrinsic:\n{intrinsic_matrix}")
        print(f"intrinsic error: {intrinsic_error}")
        print(f"rotation: {extrinsic.rotation}")
        print(f"translation: {extrinsic.translation}")
        print(f"extrinsic error: {extrinsic_error}")
        print(f"distortion: {distortion}")
        print(f"distortion error: {distortion_error}")
        print(f"nozzle: x={nozzle.x} y={nozzle.y} z={nozzle.z}")


if __name__ == "__main__":
    run_cli()
