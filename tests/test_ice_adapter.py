# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the optional ZeroC Ice adapter and client."""

from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np
import pytest

Ice = pytest.importorskip("Ice")

import station_calibration.ice.adapter as adapter_module  # noqa: E402
import station_calibration.service as service_module  # noqa: E402
from station_calibration.ice.adapter import CalibrationIceServant  # noqa: E402
from station_calibration.ice.client import CalibrationIceClient  # noqa: E402
from station_calibration.ice.images import (  # noqa: E402
    array_from_image_data,
    image_data_from_array,
)
from Phenoseeder import Point  # noqa: E402
from Phyto.Common import (  # noqa: E402
    EXTRINSICMODEL,
    IMAGEDATATYPE,
    IMAGEFORMAT,
    INTRINSICMODEL,
    imageData,
)


class FakeService:
    def __init__(self) -> None:
        self.last_result = _fake_result()
        self.ready = True
        self.images: list[tuple[np.ndarray, np.ndarray, str | None]] = []
        self.error_calls: list[int] = []
        self.session = SimpleNamespace(fit_observations=[object()])

    @property
    def is_ready(self) -> bool:
        return self.ready

    def finish_if_ready(self):
        return self.last_result if self.ready else None

    def add_image_array(
        self,
        image: np.ndarray,
        robot_position: np.ndarray,
        *,
        source: str | None = None,
        fit: bool | None = None,
    ) -> None:
        self.images.append(
            (np.asarray(image), np.asarray(robot_position), source)
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

    def fake_calculate_errors(*args, **kwargs):
        service.error_calls.append(1)
        return (
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
        )

    monkeypatch.setattr(
        adapter_module,
        "calculate_calibration_errors",
        fake_calculate_errors,
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

    def _factory(settings):
        settings.fix_cx_cy = False
        return service

    servant = CalibrationIceServant(
        tmp_path,
        service_factory=_factory,
    )
    return servant, service


def test_adapter_maps_results_to_ice_types(tmp_path, monkeypatch) -> None:
    servant, service = _make_servant(tmp_path, monkeypatch)

    intrinsic, intrinsic_error = servant.getIntrinsic()
    assert intrinsic.modelId is INTRINSICMODEL.INTRINSICMATRIX
    assert intrinsic.modelParams == pytest.approx(
        [100.0, 0.0, 10.0, 0.0, 200.0, 20.0, 0.0, 0.0, 1.0]
    )
    assert intrinsic_error == pytest.approx(
        [1.0, 0.0, 2.0, 0.0, 3.0, 4.0, 0.0, 0.0, 0.0]
    )

    extrinsic, extrinsic_error = servant.getExtrinsic()
    assert extrinsic.modelId is EXTRINSICMODEL.EXTRINSICROTMATRIX
    assert extrinsic.modelParams == pytest.approx(
        [1.0, 2.0, 3.0, *np.eye(3).reshape(-1).tolist()]
    )
    assert extrinsic_error == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])

    distortion, distortion_error = servant.getDistortion()
    assert distortion == pytest.approx([0.0, 1.0, 2.0, 3.0])
    assert distortion_error == pytest.approx([0.0, 0.1, 0.2, 0.3])
    assert len(service.error_calls) == 1

    nozzle = servant.getOptimalNozzlePosition()
    assert (nozzle.x, nozzle.y, nozzle.z) == pytest.approx((7.0, 8.0, 9.0))

    assert servant.isReady() is True
    assert servant.calibrate() == []

    frame = np.arange(2 * 3 * 3, dtype=np.uint8).reshape(2, 3, 3)
    servant.addData(
        Point(x=4.0, y=5.0, z=6.0),
        imageData(
            height=2,
            width=3,
            spp=3,
            imgformat=IMAGEFORMAT.PMBGR,
            imgDataType=IMAGEDATATYPE.IDTBYTE,
            bytePixels=frame.tobytes(),
        ),
    )
    assert len(service.images) == 1
    image, robot_position, source = service.images[0]
    np.testing.assert_array_equal(image, frame)
    np.testing.assert_allclose(robot_position, [4.0, 5.0, 6.0])
    assert source == "ice"


def test_adapter_add_data_turns_analysis_failure_into_rejection(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(service_module, "split_image", lambda image: (image, None))

    def fail_analysis(image_gray, image_color, **kwargs):
        raise RuntimeError("bad frame")

    monkeypatch.setattr(service_module, "analyze_image", fail_analysis)

    servant = CalibrationIceServant(tmp_path)
    frame = np.zeros((2, 3), dtype=np.uint8)

    servant.addData(
        Point(x=1.0, y=2.0, z=3.0),
        imageData(
            height=2,
            width=3,
            spp=1,
            imgformat=IMAGEFORMAT.PMBGR,
            imgDataType=IMAGEDATATYPE.IDTBYTE,
            bytePixels=frame.tobytes(),
        ),
    )

    service = servant._require_service()
    assert service.session.n_observations == 0
    assert service.session.n_rejections == 1
    assert "image analysis failed" in service.session.rejections[0].reason


def test_adapter_init_accepts_folder(tmp_path, monkeypatch) -> None:
    servant, _ = _make_servant(tmp_path, monkeypatch)

    other_folder = tmp_path / "other"
    other_folder.mkdir()
    servant.init(str(other_folder))
    assert servant.folder == tmp_path.resolve()
    assert servant._settings.main_folder == other_folder.resolve()


@pytest.mark.parametrize("dtype", [np.bool_, np.uint8, np.int16, np.float32])
def test_image_wire_round_trip(dtype) -> None:
    if dtype is np.bool_:
        frame = np.array([[True, False, True], [False, True, False]])
    else:
        frame = np.arange(6, dtype=dtype).reshape(2, 3)

    decoded = array_from_image_data(image_data_from_array(frame))

    assert decoded.dtype == dtype
    np.testing.assert_array_equal(decoded, frame)


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
            intrinsic_matrix = np.asarray(
                intrinsic.modelParams,
                dtype=np.float64,
            ).reshape(3, 3)
            assert intrinsic_matrix[0, 0] == pytest.approx(100.0)
            assert intrinsic_matrix[1, 1] == pytest.approx(200.0)
            assert intrinsic_matrix[0, 2] == pytest.approx(10.0)
            assert intrinsic_matrix[1, 2] == pytest.approx(20.0)
            assert intrinsic_error == pytest.approx(
                [1.0, 0.0, 2.0, 0.0, 3.0, 4.0, 0.0, 0.0, 0.0]
            )

            frame = np.arange(4 * 5, dtype=np.uint8).reshape(4, 5)
            client.add_image(frame, (1.0, 2.0, 3.0))
            np.testing.assert_array_equal(service.images[-1][0], frame)

            encoded_ok, encoded = cv2.imencode(".png", frame)
            assert encoded_ok
            client.add_image(encoded.tobytes(), (1.0, 2.0, 3.0))
            np.testing.assert_array_equal(service.images[-1][0], frame)

            nozzle = client.get_optimal_nozzle_position()
            assert (nozzle.x, nozzle.y, nozzle.z) == pytest.approx((7.0, 8.0, 9.0))

        with CalibrationIceClient.connect(proxy.ice_toString()) as connected:
            connected.init(None)
            assert connected.is_ready() is True
    finally:
        communicator.destroy()
