# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0

"""Tests for the optional ZeroC Ice adapter and client."""

from __future__ import annotations

import csv
import re
import shutil
import struct
import tomllib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import yaml

Ice = pytest.importorskip("Ice")

import station_calibration.ice.adapter as adapter_module  # noqa: E402
import station_calibration.service as service_module  # noqa: E402
from station_calibration.ice.adapter import CalibrationIceServant  # noqa: E402
from station_calibration.ice.archive import (  # noqa: E402
    TIFF_COMPRESSION,
    SessionArchive,
)
from station_calibration.ice import server as ice_server  # noqa: E402
from station_calibration.ice.client import CalibrationIceClient  # noqa: E402
from station_calibration.ice.procedures import (  # noqa: E402
    ProcedureRegistry,
    deep_merge,
    dumps_toml,
    load_procedures_root,
)
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
        self.finish_calls = 0
        self.finish_error: Exception | None = None
        self.session = SimpleNamespace(fit_observations=[object()])

    @property
    def is_ready(self) -> bool:
        return self.ready

    def finish(self):
        self.finish_calls += 1
        if self.finish_error is not None:
            raise self.finish_error
        return self.last_result

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
        image_size_xy=(3, 2),
        observation_count=1,
        n_used=1,
        fit_mask=np.ones(1, dtype=bool),
        rmse=0.25,
    )


def _make_procedure_root(
    tmp_path: Path,
    *,
    procedure_ids: tuple[int, ...] = (1,),
) -> Path:
    root = tmp_path / "procedures"
    root.mkdir()
    for procedure_id in procedure_ids:
        procedure_dir = root / str(procedure_id)
        procedure_dir.mkdir()
        shutil.copy(
            adapter_module.Settings.DEFAULT_CONFIG_FILE,
            procedure_dir / "config.toml",
        )
    return root


def _make_servant(
    tmp_path: Path,
    monkeypatch,
    *,
    procedures_root: Path | None = None,
    procedure_ids: tuple[int, ...] = (1,),
) -> tuple[CalibrationIceServant, FakeService]:
    root = procedures_root or _make_procedure_root(
        tmp_path,
        procedure_ids=procedure_ids,
    )
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
        root,
        service_factory=_factory,
    )
    return servant, service


def test_adapter_maps_results_to_ice_types(tmp_path, monkeypatch) -> None:
    servant, service = _make_servant(tmp_path, monkeypatch)
    servant.init(1)

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


def test_adapter_nozzle_estimation_uses_fit_inliers(tmp_path, monkeypatch) -> None:
    servant, service = _make_servant(tmp_path, monkeypatch)
    result = _fake_result()
    result.fit_mask = np.array([True, False, True], dtype=bool)
    result.center_points_adjusted = np.array(
        [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
        dtype=np.float64,
    )
    service.session.fit_observations = [object(), object(), object()]

    captured: dict[str, object] = {}

    def fake_observations(observations):
        observations = tuple(observations)
        captured["n_observations"] = len(observations)
        n = len(observations)
        return (
            np.zeros((n, 3), dtype=np.float64),
            np.zeros((n, 2), dtype=np.float64),
            np.ones(n, dtype=np.float64),
            np.ones(n, dtype=np.float64),
            np.ones(n, dtype=np.int8),
        )

    def fake_nozzle(**kwargs):
        captured["kwargs"] = kwargs
        return np.array([1.0, 2.0, 3.0]), 2.0, {}

    monkeypatch.setattr(adapter_module, "observations_to_arrays", fake_observations)
    monkeypatch.setattr(adapter_module, "get_nozzle_end_home_position", fake_nozzle)

    nozzle = servant._estimate_nozzle_position(service, result)

    np.testing.assert_allclose(nozzle, [1.0, 2.0, 3.0])
    assert captured["n_observations"] == 2
    kwargs = captured["kwargs"]
    assert kwargs["image_center_points"].shape == (2, 2)
    np.testing.assert_allclose(
        kwargs["image_center_points"],
        [[1.0, 2.0], [5.0, 6.0]],
    )
    assert kwargs["radii"].shape == (2,)
    assert kwargs["sigmas"].shape == (2,)


def test_adapter_archives_session_images_csv_and_result(
    tmp_path,
    monkeypatch,
) -> None:
    servant, _service = _make_servant(tmp_path, monkeypatch)
    session = Path(servant.init(1))
    data = session / "data"
    frame = np.arange(2 * 3, dtype=np.uint8).reshape(2, 3)

    servant.addData(
        Point(x=4.0, y=5.0, z=6.0),
        imageData(
            height=2,
            width=3,
            spp=1,
            imgformat=IMAGEFORMAT.PMBGGR,
            imgDataType=IMAGEDATATYPE.IDTBYTE,
            bytePixels=frame.tobytes(),
        ),
    )
    servant.getIntrinsic()
    servant.close()

    assert (session / "config.toml").is_file()
    assert data.is_dir()
    assert re.fullmatch(r"\d{8}_\d{4}(?:_\d{2})?", session.name)

    image_path = data / "image_0001.tif"
    assert image_path.is_file()
    np.testing.assert_array_equal(
        cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED),
        frame,
    )

    with (data / "Calibration3DPositions.csv").open(newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0][0] == "calibration session"
    assert rows[1] == ["4", "5", "6", "image_0001.tif"]

    result = yaml.safe_load(
        (data / "calibration_result.yaml").read_text(encoding="utf-8")
    )
    assert result["schema_version"] == 1
    assert result["nozzle"]["home_position"] is None
    assert result["camera"]["intrinsic_matrix"][0][0] == pytest.approx(100.0)
    assert "errors" in result["camera"]
    assert result["session"]["image_count"] == 1
    assert result["session"]["procedure_id"] == 1
    assert result["session"]["config_file"] == str(session / "config.toml")

    metadata = yaml.safe_load(
        (data / "session.yaml").read_text(encoding="utf-8")
    )
    assert metadata["session"]["image_count"] == 1
    assert metadata["session"]["ended_at"] is not None
    assert metadata["session"]["procedure_id"] == 1
    assert metadata["session"]["session_folder"] == str(session)
    assert metadata["session"]["config_file"] == str(session / "config.toml")


@pytest.mark.parametrize(
    "frame",
    [
        np.array([[1000, 2000], [3000, 4000]], dtype=np.uint16),
        np.array([[1000, 2000], [3000, 4000]], dtype=np.int16),
        np.array([[1.5, 2.5], [3.5, 4.5]], dtype=np.float32),
    ],
)
def test_session_archive_preserves_wide_frame_dtype(tmp_path, frame) -> None:
    archive = SessionArchive(tmp_path)
    archive.record(frame, np.zeros(3, dtype=np.float64))
    session_dir = archive.session_dir
    assert session_dir == tmp_path
    archive.close()

    saved = cv2.imread(
        str(session_dir / "image_0001.tif"),
        cv2.IMREAD_UNCHANGED,
    )
    assert saved.dtype == frame.dtype
    np.testing.assert_array_equal(saved, frame)


def test_session_archive_compresses_tiff(tmp_path) -> None:
    archive = SessionArchive(tmp_path)
    frame = np.zeros((256, 256), dtype=np.uint16)
    frame[::2, ::2] = 4000
    archive.record(frame, np.zeros(3, dtype=np.float64))
    archive.close()

    image_path = tmp_path / "image_0001.tif"
    assert _tiff_compression(image_path) == TIFF_COMPRESSION
    assert image_path.stat().st_size < frame.nbytes // 4


def test_session_archive_stores_boolean_frames_as_uint8(tmp_path) -> None:
    archive = SessionArchive(tmp_path)
    frame = np.array([[True, False], [False, True]])
    archive.record(frame, np.zeros(3, dtype=np.float64))
    archive.close()

    saved = cv2.imread(
        str(tmp_path / "image_0001.tif"),
        cv2.IMREAD_UNCHANGED,
    )
    assert saved.dtype == np.uint8
    np.testing.assert_array_equal(saved, frame.astype(np.uint8) * 255)


def _tiff_compression(path: Path) -> int:
    """Read the TIFF Compression tag (259) from a single-image file."""
    payload = path.read_bytes()
    endian = "<" if payload[:2] == b"II" else ">"
    ifd_offset = struct.unpack_from(f"{endian}I", payload, 4)[0]
    entry_count = struct.unpack_from(f"{endian}H", payload, ifd_offset)[0]
    for index in range(entry_count):
        entry_offset = ifd_offset + 2 + index * 12
        tag, kind, count, value = struct.unpack_from(
            f"{endian}HHI4s",
            payload,
            entry_offset,
        )
        if tag == 259:
            assert kind == 3 and count == 1
            return struct.unpack(f"{endian}H", value[:2])[0]
    return 1


def test_adapter_add_data_turns_analysis_failure_into_rejection(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(service_module, "split_image", lambda image: (image, None))

    def fail_analysis(image_gray, image_color, **kwargs):
        raise RuntimeError("bad frame")

    monkeypatch.setattr(service_module, "analyze_image", fail_analysis)

    root = _make_procedure_root(tmp_path)
    servant = CalibrationIceServant(root)
    servant.init(1)
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


def test_procedure_registry_creates_session_layout(tmp_path) -> None:
    root = _make_procedure_root(tmp_path)
    registry = ProcedureRegistry(root)
    now = datetime(2026, 11, 4, 12, 34)

    session = registry.create_session(1, now=now)

    assert session.procedure_id == 1
    assert session.procedure_dir == root / "1"
    assert session.session_dir == root / "1" / "20261104_1234"
    assert session.config_file == session.session_dir / "config.toml"
    assert session.data_dir == session.session_dir / "data"
    assert session.data_dir.is_dir()
    assert session.override_config_file is None

    default = tomllib.loads(
        (root / "1" / "config.toml").read_text(encoding="utf-8")
    )
    written = tomllib.loads(session.config_file.read_text(encoding="utf-8"))
    assert written == default

    second = registry.create_session(1, now=now)
    assert second.session_dir.name == "20261104_1234_01"
    assert second.data_dir.is_dir()


def test_procedure_registry_merges_override_recursively(tmp_path) -> None:
    root = tmp_path / "procedures"
    procedure_dir = root / "1"
    procedure_dir.mkdir(parents=True)
    default = {
        "general": {
            "archive_sessions": True,
            "files": {
                "output_folder": "out",
                "image_name_patterns": ["*.tif"],
            },
        },
        "analysis": {
            "n_iterations": 3,
            "fit": {"fix_cx_cy": True},
        },
        "custom": {"keep": 1, "replace": "old", "values": [1, 2, 3]},
    }
    (procedure_dir / "config.toml").write_text(
        dumps_toml(default),
        encoding="utf-8",
    )
    override_file = tmp_path / "override.toml"
    override_file.write_text(
        dumps_toml(
            {
                "general": {"files": {"image_name_patterns": ["*.png"]}},
                "analysis": {"fit": {"fix_cx_cy": False}},
                "custom": {"replace": "new", "values": [9], "added": 2},
            }
        ),
        encoding="utf-8",
    )

    session = ProcedureRegistry(root).create_session(1, override_file)
    merged = tomllib.loads(session.config_file.read_text(encoding="utf-8"))

    assert merged["general"]["archive_sessions"] is True
    assert merged["general"]["files"]["output_folder"] == "out"
    assert merged["general"]["files"]["image_name_patterns"] == ["*.png"]
    assert merged["analysis"]["n_iterations"] == 3
    assert merged["analysis"]["fit"]["fix_cx_cy"] is False
    assert merged["custom"]["keep"] == 1
    assert merged["custom"]["replace"] == "new"
    assert merged["custom"]["values"] == [9]
    assert merged["custom"]["added"] == 2
    assert session.override_config_file == override_file
    assert deep_merge({"a": {"b": 1}}, {"a": {"c": 2}}) == {
        "a": {"b": 1, "c": 2}
    }


def test_procedure_registry_rejects_relative_override(tmp_path) -> None:
    root = _make_procedure_root(tmp_path)
    registry = ProcedureRegistry(root)

    with pytest.raises(ValueError, match="absolute"):
        registry.create_session(1, "config.toml")
    with pytest.raises(TypeError, match="integer"):
        registry.create_session("1")  # type: ignore[arg-type]


def test_procedure_registry_auto_creates_missing_procedure(tmp_path) -> None:
    root = tmp_path / "procedures"
    root.mkdir()

    session = ProcedureRegistry(root).create_session(5)

    procedure_config = root / "5" / "config.toml"
    assert procedure_config.is_file()
    assert procedure_config.read_bytes() == (
        adapter_module.Settings.DEFAULT_CONFIG_FILE.read_bytes()
    )
    assert session.default_config_file == procedure_config
    assert tomllib.loads(session.config_file.read_text(encoding="utf-8")) == (
        tomllib.loads(procedure_config.read_text(encoding="utf-8"))
    )


def test_procedure_registry_new_procedure_persists_override(tmp_path) -> None:
    root = tmp_path / "procedures"
    root.mkdir()
    override = tmp_path / "override.toml"
    override.write_text(
        dumps_toml({"analysis": {"fit": {"fix_cx_cy": False}}}),
        encoding="utf-8",
    )

    session = ProcedureRegistry(root).create_session(6, override)

    procedure_config = tomllib.loads(
        (root / "6" / "config.toml").read_text(encoding="utf-8")
    )
    session_config = tomllib.loads(
        session.config_file.read_text(encoding="utf-8")
    )
    assert procedure_config["analysis"]["fit"]["fix_cx_cy"] is False
    assert procedure_config["general"]["files"]["output_folder"] == "output"
    assert session_config == procedure_config


def test_procedure_registry_existing_override_is_session_only(tmp_path) -> None:
    root = _make_procedure_root(tmp_path)
    procedure_config = root / "1" / "config.toml"
    before = procedure_config.read_bytes()
    override = tmp_path / "override.toml"
    override.write_text(
        dumps_toml({"analysis": {"fit": {"fix_cx_cy": False}}}),
        encoding="utf-8",
    )

    session = ProcedureRegistry(root).create_session(1, override)

    assert tomllib.loads(
        session.config_file.read_text(encoding="utf-8")
    )["analysis"]["fit"]["fix_cx_cy"] is False
    assert procedure_config.read_bytes() == before


def test_load_procedures_root(tmp_path) -> None:
    root = tmp_path / "procedures"
    root.mkdir()
    server_config = tmp_path / "server.toml"
    server_config.write_text(
        dumps_toml({"general": {"procedures_root": str(root)}}),
        encoding="utf-8",
    )

    assert load_procedures_root(server_config) == root.resolve()

    missing = tmp_path / "missing.toml"
    missing.write_text("[general]\n", encoding="utf-8")
    with pytest.raises(KeyError, match="procedures_root"):
        load_procedures_root(missing)

    relative = tmp_path / "relative.toml"
    relative.write_text(
        dumps_toml({"general": {"procedures_root": "relative/path"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="absolute"):
        load_procedures_root(relative)


def test_dumps_toml_round_trips_default_config() -> None:
    data = tomllib.loads(
        adapter_module.Settings.DEFAULT_CONFIG_FILE.read_text(encoding="utf-8")
    )
    assert tomllib.loads(dumps_toml(data)) == data


def test_ice_server_cli_requires_config(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "server.toml"
    captured = {}

    def fake_run_server(config_file, **kwargs):
        captured["config_file"] = config_file
        captured.update(kwargs)

    monkeypatch.setattr(ice_server, "run_server", fake_run_server)

    ice_server.run_cli(["--config", str(config_file)])

    assert captured["config_file"] == config_file
    assert (
        captured["message_size_max_kb"]
        == ice_server.DEFAULT_MESSAGE_SIZE_MAX_KB
    )


def test_ice_server_raises_ice_message_size_limit(tmp_path, monkeypatch) -> None:
    root = tmp_path / "procedures"
    root.mkdir()
    config_file = tmp_path / "server.toml"
    config_file.write_text(
        f"[general]\nprocedures_root = '{root.as_posix()}'\n",
        encoding="utf-8",
    )
    captured: dict[str, list[str]] = {}

    class FakeAdapter:
        def add(self, servant, identity):
            return None

        def activate(self) -> None:
            return None

    class FakeCommunicator:
        def createObjectAdapterWithEndpoints(self, name, endpoint):
            return FakeAdapter()

        def waitForShutdown(self) -> None:
            return None

        def destroy(self) -> None:
            return None

    def fake_initialize(args):
        captured["args"] = list(args)
        return FakeCommunicator()

    monkeypatch.setattr(Ice, "initialize", fake_initialize)

    ice_server.run_server(config_file)

    assert (
        f"--Ice.MessageSizeMax={ice_server.DEFAULT_MESSAGE_SIZE_MAX_KB}"
        in captured["args"]
    )


def test_ice_server_signal_handler_shuts_down_communicator(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "procedures"
    root.mkdir()
    config_file = tmp_path / "server.toml"
    config_file.write_text(
        f"[general]\nprocedures_root = '{root.as_posix()}'\n",
        encoding="utf-8",
    )
    captured: dict[str, bool] = {}
    installed: dict[int, object] = {}

    class FakeAdapter:
        def add(self, servant, identity):
            return None

        def activate(self) -> None:
            return None

    class FakeCommunicator:
        def createObjectAdapterWithEndpoints(self, name, endpoint):
            return FakeAdapter()

        def waitForShutdown(self) -> None:
            captured["waited"] = True

        def shutdown(self) -> None:
            captured["shutdown"] = True

        def destroy(self) -> None:
            captured["destroyed"] = True

    monkeypatch.setattr(Ice, "initialize", lambda args: FakeCommunicator())

    def fake_getsignal(signum):
        return "old-handler"

    def fake_signal(signum, handler):
        if callable(handler):
            installed[signum] = handler
        return "old-handler"

    monkeypatch.setattr(ice_server.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(ice_server.signal, "signal", fake_signal)

    ice_server.run_server(config_file)

    sigterm = ice_server.signal.SIGTERM
    assert sigterm in installed
    installed[sigterm](sigterm, None)

    assert captured["waited"] is True
    assert captured["shutdown"] is True
    assert captured["destroyed"] is True


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(7, 7), (0, None)],
)
def test_adapter_uses_configured_fit_every_n(
    tmp_path,
    configured,
    expected,
) -> None:
    root = _make_procedure_root(tmp_path)
    config_path = root / "1" / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    config["analysis"]["fit_every_n"] = configured
    config_path.write_text(dumps_toml(config), encoding="utf-8")

    servant = CalibrationIceServant(root)
    servant.init(1)

    assert servant._require_service().session.fit_every_n == expected


def test_adapter_init_returns_date_folder_and_merged_config(
    tmp_path,
    monkeypatch,
) -> None:
    root = _make_procedure_root(tmp_path)
    override_file = tmp_path / "override.toml"
    override_file.write_text(
        dumps_toml(
            {"analysis": {"fit": {"fix_cx_cy": False}}}
        ),
        encoding="utf-8",
    )
    servant, _service = _make_servant(
        tmp_path,
        monkeypatch,
        procedures_root=root,
    )

    returned = Path(servant.init(1, str(override_file)))

    assert returned.is_absolute()
    assert returned.parent == root / "1"
    assert re.fullmatch(r"\d{8}_\d{4}(?:_\d{2})?", returned.name)
    assert servant.active_procedure_id == 1
    assert servant.procedure_session is not None
    assert servant.procedure_session.config_file == returned / "config.toml"
    assert servant.procedure_session.data_dir == returned / "data"
    assert servant._settings.main_folder == returned / "data"

    merged = tomllib.loads((returned / "config.toml").read_text(encoding="utf-8"))
    assert merged["analysis"]["fit"]["fix_cx_cy"] is False
    assert merged["analysis"]["n_iterations"] == 3


def test_adapter_init_auto_creates_missing_procedure(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "procedures"
    root.mkdir()
    servant, _service = _make_servant(
        tmp_path,
        monkeypatch,
        procedures_root=root,
    )

    returned = Path(servant.init(3))

    assert (root / "3" / "config.toml").is_file()
    assert returned.parent == root / "3"
    assert servant.active_procedure_id == 3
    assert servant.procedure_session is not None
    assert servant.procedure_session.default_config_file == (
        root / "3" / "config.toml"
    )


def test_adapter_uninitialized_behavior(tmp_path) -> None:
    root = _make_procedure_root(tmp_path)
    servant = CalibrationIceServant(root)

    assert servant.finish() is False
    servant.abort()
    assert servant.active_procedure_id is None
    assert servant.isReady() is False
    with pytest.raises(RuntimeError, match="init first"):
        servant.getIntrinsic()
    with pytest.raises(RuntimeError, match="init first"):
        servant.addData(
            Point(x=1.0, y=2.0, z=3.0),
            imageData(
                height=2,
                width=3,
                spp=1,
                imgformat=IMAGEFORMAT.PMBGR,
                imgDataType=IMAGEDATATYPE.IDTBYTE,
                bytePixels=np.zeros((2, 3), dtype=np.uint8).tobytes(),
            ),
        )


def test_adapter_missing_config_path_raises(tmp_path) -> None:
    root = _make_procedure_root(tmp_path)
    servant = CalibrationIceServant(root)

    with pytest.raises(FileNotFoundError, match="override file not found"):
        servant.init(1, str(tmp_path / "missing.toml"))


def test_adapter_rejects_procedure_switch_during_active_calibration(
    tmp_path,
    monkeypatch,
) -> None:
    root = _make_procedure_root(tmp_path, procedure_ids=(1, 2))
    servant, service = _make_servant(
        tmp_path,
        monkeypatch,
        procedures_root=root,
    )
    servant.init(1)
    service.ready = False
    frame = np.zeros((2, 3), dtype=np.uint8)
    servant.addData(
        Point(x=1.0, y=2.0, z=3.0),
        imageData(
            height=2,
            width=3,
            spp=1,
            imgformat=IMAGEFORMAT.PMBGGR,
            imgDataType=IMAGEDATATYPE.IDTBYTE,
            bytePixels=frame.tobytes(),
        ),
    )

    with pytest.raises(RuntimeError, match="active calibration"):
        servant.init(2)

    service.ready = True
    with pytest.raises(RuntimeError, match="active calibration"):
        servant.init(2)

    assert servant.finish() is True
    servant.init(2)
    assert servant.active_procedure_id == 2


def test_adapter_rejects_same_procedure_init_until_finish_or_abort(
    tmp_path,
    monkeypatch,
) -> None:
    servant, service = _make_servant(tmp_path, monkeypatch)
    servant.init(1)
    service.ready = False
    frame = np.zeros((2, 3), dtype=np.uint8)
    servant.addData(
        Point(x=1.0, y=2.0, z=3.0),
        imageData(
            height=2,
            width=3,
            spp=1,
            imgformat=IMAGEFORMAT.PMBGGR,
            imgDataType=IMAGEDATATYPE.IDTBYTE,
            bytePixels=frame.tobytes(),
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        servant.init(1)

    message = str(exc_info.value)
    assert "active calibration" in message
    assert "finish()" in message
    assert "abort()" in message

    assert servant.finish() is True
    servant.init(1)
    assert servant.active_procedure_id == 1


def test_adapter_finish_forces_result_and_allows_switch(
    tmp_path,
    monkeypatch,
) -> None:
    root = _make_procedure_root(tmp_path, procedure_ids=(1, 2))
    servant, service = _make_servant(
        tmp_path,
        monkeypatch,
        procedures_root=root,
    )
    session = Path(servant.init(1))
    service.ready = False
    frame = np.zeros((2, 3), dtype=np.uint8)
    servant.addData(
        Point(x=1.0, y=2.0, z=3.0),
        imageData(
            height=2,
            width=3,
            spp=1,
            imgformat=IMAGEFORMAT.PMBGGR,
            imgDataType=IMAGEDATATYPE.IDTBYTE,
            bytePixels=frame.tobytes(),
        ),
    )

    assert servant.isReady() is False
    assert servant.finish() is True
    assert service.finish_calls == 1
    assert servant.isReady() is True
    assert (session / "data" / "calibration_result.yaml").is_file()

    servant.init(2)
    assert servant.active_procedure_id == 2


def test_adapter_finish_returns_false_without_result(
    tmp_path,
    monkeypatch,
) -> None:
    root = _make_procedure_root(tmp_path)
    servant, service = _make_servant(
        tmp_path,
        monkeypatch,
        procedures_root=root,
    )

    assert servant.finish() is False

    servant.init(1)
    service.ready = False
    service.finish_error = ValueError("too few observations")
    assert servant.finish() is False
    assert servant.isReady() is False


def test_adapter_abort_discards_session_and_allows_switch(
    tmp_path,
    monkeypatch,
) -> None:
    root = _make_procedure_root(tmp_path, procedure_ids=(1, 2))
    servant, service = _make_servant(
        tmp_path,
        monkeypatch,
        procedures_root=root,
    )
    session = Path(servant.init(1))
    service.ready = False
    frame = np.zeros((2, 3), dtype=np.uint8)
    servant.addData(
        Point(x=1.0, y=2.0, z=3.0),
        imageData(
            height=2,
            width=3,
            spp=1,
            imgformat=IMAGEFORMAT.PMBGGR,
            imgDataType=IMAGEDATATYPE.IDTBYTE,
            bytePixels=frame.tobytes(),
        ),
    )

    servant.abort()

    assert servant.active_procedure_id is None
    assert servant.procedure_session is None
    assert servant._service is None
    assert servant.isReady() is False
    metadata = yaml.safe_load(
        (session / "data" / "session.yaml").read_text(encoding="utf-8")
    )
    assert metadata["session"]["ended_at"] is not None

    servant.init(2)
    assert servant.active_procedure_id == 2


def test_procedure_id_uses_unpadded_folder_name(tmp_path, monkeypatch) -> None:
    root = _make_procedure_root(tmp_path, procedure_ids=(7,))
    servant, _service = _make_servant(
        tmp_path,
        monkeypatch,
        procedures_root=root,
    )

    returned = Path(servant.init(7))

    assert returned.parent.name == "7"


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
            session_folder = client.init(1)
            assert Path(session_folder).is_dir()
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

            assert client.finish() is True
            client.abort()
            assert client.is_ready() is False

        with CalibrationIceClient.connect(proxy.ice_toString()) as connected:
            connected.init(1)
            assert connected.is_ready() is True
    finally:
        communicator.destroy()
