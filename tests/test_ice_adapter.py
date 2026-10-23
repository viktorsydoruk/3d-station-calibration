# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the optional ZeroC Ice adapter and client."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

Ice = pytest.importorskip("Ice")

import station_calibration.ice.adapter as adapter_module  # noqa: E402
from station_calibration.ice.adapter import CalibrationIceServant  # noqa: E402
from station_calibration.ice.client import CalibrationIceClient  # noqa: E402
from Phenoseeder import Point  # noqa: E402
from Phyto.Common import imageData  # noqa: E402


class FakeService:
    def __init__(self) -> None:
        self.last_result = _fake_result()
        self.ready = True
        self.images: list[tuple[bytes, np.ndarray, str | None]] = []
        self.session = SimpleNamespace(fit_observations=[object()])

    @property
    def is_ready(self) -> bool:
        return self.ready

    def finish_if_ready(self):
        return self.last_result if self.ready else None

    def add_image_bytes(
        self,
        image_bytes: bytes,
        robot_position: np.ndarray,
        *,
        source: str | None = None,
        fit: bool | None = None,
    ) -> None:
        self.images.append(
            (bytes(image_bytes), np.asarray(robot_position), source)
        )


def _fake_result():
    intrinsic = np.array(
        [
            [100.0, 0.0, 10.0],
            [0.0, 200.0, 20.0],
            [0.0, 0.0, 1.0],
        ]
    )
    extrinsic = np.eye(4)
    extrinsic[:3, 3] = [1.0, 2.0, 3.0]
    distortion = np.arange(14, dtype=np.float64)
    return SimpleNamespace(
        intrinsic_matrix=intrinsic,
        extrinsic_matrix=extrinsic,
        distortion=distortion,
        n_distortion_coefs=4,
        optimize_result=SimpleNamespace(),
        pos_home=np.zeros(3, dtype=np.float64),
        center_points_adjusted=np.zeros((1, 2), dtype=np.float64),
        observation_count=1,
        n_used=1,
    )


def _make_servant(tmp_path, monkeypatch) -> tuple[CalibrationIceServant, FakeService]:
    service = FakeService()

    monkeypatch.setattr(
        adapter_module,
        "calculate_calibration_errors",
        lambda *args, **kwargs: (
            np.array(
                [
                    [1.0, 0.0, 2.0],
                    [0.0, 3.0, 4.0],
                    [0.0, 0.0, 1.0],
                ]
            ),
            np.arange(14, dtype=np.float64) * 0.1,
            np.array([0.1, 0.2, 0.3]),
            np.array([0.4, 0.5, 0.6]),
        ),
    )
    monkeypatch.setattr(
        adapter_module,
        "observations_to_arrays",
        lambda observations: (
            np.zeros((1, 3), dtype=np.float64),
            np.zeros((1, 2), dtype=np.float64),
            np.ones(1, dtype=np.float64),
            np.ones(1, dtype=np.float64),
            np.ones(1, dtype=np.int8),
        ),
    )
    monkeypatch.setattr(
        adapter_module,
        "get_nozzle_end_home_position",
        lambda **kwargs: (np.array([7.0, 8.0, 9.0]), 2.0, {}),
    )

    servant = CalibrationIceServant(
        tmp_path,
        service_factory=lambda settings: service,
    )
    return servant, service


def test_adapter_maps_results_to_ice_types(tmp_path, monkeypatch) -> None:
    servant, service = _make_servant(tmp_path, monkeypatch)

    intrinsic, intrinsic_error = servant.getIntrinsic()
    assert intrinsic.fx == pytest.approx(100.0)
    assert intrinsic.fy == pytest.approx(200.0)
    assert intrinsic.cx == pytest.approx(10.0)
    assert intrinsic.cy == pytest.approx(20.0)
    assert intrinsic_error == pytest.approx([1.0, 3.0, 2.0, 4.0])

    extrinsic, extrinsic_error = servant.getExtrinsic()
    assert extrinsic.rotation == pytest.approx(np.eye(3).reshape(-1).tolist())
    assert extrinsic.translation == pytest.approx([1.0, 2.0, 3.0])
    assert extrinsic_error == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])

    distortion, distortion_error = servant.getDistortion()
    assert distortion == pytest.approx([0.0, 1.0, 2.0, 3.0])
    assert distortion_error == pytest.approx([0.0, 0.1, 0.2, 0.3])

    nozzle = servant.getOptimalNozzlePosition()
    assert (nozzle.x, nozzle.y, nozzle.z) == pytest.approx((7.0, 8.0, 9.0))

    assert servant.isReady() is True
    assert servant.calibrate() == []

    servant.addData(
        Point(x=4.0, y=5.0, z=6.0),
        imageData(data=b"image-bytes", width=10, height=20, channels=3),
    )
    assert len(service.images) == 1
    image_bytes, robot_position, source = service.images[0]
    assert image_bytes == b"image-bytes"
    np.testing.assert_allclose(robot_position, [4.0, 5.0, 6.0])
    assert source == "ice"


def test_adapter_init_accepts_folder(tmp_path, monkeypatch) -> None:
    servant, _ = _make_servant(tmp_path, monkeypatch)

    other_folder = tmp_path / "other"
    other_folder.mkdir()
    servant.init(str(other_folder))
    assert servant.folder == tmp_path.resolve()
    assert servant._settings.main_folder == other_folder.resolve()


def test_ice_round_trip(tmp_path, monkeypatch) -> None:
    servant, service = _make_servant(tmp_path, monkeypatch)

    communicator = Ice.initialize([])
    try:
        adapter = communicator.createObjectAdapterWithEndpoints(
            "CalibrationTestAdapter",
            "tcp -h 127.0.0.1 -p 0",
        )
        proxy = adapter.add(
            servant,
            Ice.stringToIdentity("CalibrationPhenoseederIcingTest"),
        )
        adapter.activate()

        with CalibrationIceClient(proxy) as client:
            client.init(None)
            assert client.is_ready() is True
            intrinsic, intrinsic_error = client.get_intrinsic()
            assert intrinsic.fx == pytest.approx(100.0)
            assert intrinsic_error == pytest.approx([1.0, 3.0, 2.0, 4.0])

            client.add_image(b"remote-image", (1.0, 2.0, 3.0))
            assert service.images[-1][0] == b"remote-image"

            nozzle = client.get_optimal_nozzle_position()
            assert (nozzle.x, nozzle.y, nozzle.z) == pytest.approx((7.0, 8.0, 9.0))

        with CalibrationIceClient.connect(proxy.ice_toString()) as connected:
            connected.init(None)
            assert connected.is_ready() is True
    finally:
        communicator.destroy()
