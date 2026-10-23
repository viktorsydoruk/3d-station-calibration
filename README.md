# 3D station calibration

Camera calibration for phenoSeeder 3D stations. A white sphere is moved through
the working volume; the images and matching robot positions are used to estimate
the camera intrinsics, distortion, the robot-to-camera transform, and the nozzle
home position.

## Install

The project uses a `src` layout. Install it in editable mode for development:

```powershell
python -m pip install -e .
```

or, with uv:

```powershell
uv sync
```

## Run the folder workflow

```powershell
3dsc "P:\3Dcalibration\3D_example"
```

The equivalent module entry point is:

```powershell
python -m station_calibration "P:\3Dcalibration\3D_example"
```

`app.py` and `python __main__.py` remain available as compatibility entry points.

Useful options:

```text
--config PATH                 TOML configuration file
--debug                       print detailed progress
--store-debug-images          write analysis/debug images
--load-stored-data / --no-load-stored-data
--target-observations N
--max-observations N
```

The default configuration ships with the package at
`src/station_calibration/resources/config.toml`. Command-line options override
individual values from that file.

## Output

The folder workflow writes its results below the analysis folder:

```text
<analysis folder>/output/all_points.dat
<analysis folder>/output/calibration_data.yaml
<analysis folder>/debug/
```

`all_points.dat` is the reusable per-image point cache. If it exists and
`load_stored_data` is enabled, the folder workflow can skip image analysis and
fit the cached observations directly.

## Architecture

```text
src/station_calibration/
├─ cli.py                 folder workflow entry point
├─ settings.py            TOML-backed settings
├─ models.py              observations, rejections, fit results
├─ session.py             source-agnostic incremental calibration session
├─ service.py             image-bytes -> analysis -> session application service
├─ stop.py                readiness/stop policy
├─ image.py               single-image and batch sphere analysis
├─ camera.py              camera model and numerical fit helpers
├─ processes.py           iterative calibration pipeline
├─ robot.py               robot geometry and nozzle home estimation
├─ support.py             line geometry and parameter uncertainty
├─ file.py                robot CSV, point cache, and YAML storage
├─ plots.py               optional debug/reporting plots
├─ sources/
│  ├─ base.py             source/dataset protocols
│  └─ folder.py           folder source adapter
├─ ice/                   Ice adapter/server/client placeholder
└─ resources/
   └─ config.toml         default configuration
```

The core rule is that `CalibrationSession` does not depend on the folder layout
or on Ice. A frontend analyzes an image, creates a `CalibrationObservation` (or
an `ImageAnalysisResult` plus robot position), and feeds it to the session. The
session owns fit policy, optional radius filtering, and readiness.

For an incremental frontend, use `CalibrationService`:

```python
from station_calibration import CalibrationService, Settings

service = CalibrationService(Settings(analysis_folder))
service.add_image_bytes(image_bytes, robot_position)

if service.is_ready:
    result = service.finish()
```

`add_image_bytes` performs the same single-image analysis as folder mode and
feeds the result into the shared session. Rejected images are recorded but do
not count toward the 500-observation stop target.

## Compatibility

The old `_3dsc_libs` package is retained as a deprecation shim. It re-exports the
new `station_calibration` API; new code should import `station_calibration`
directly. The Ice contract is not implemented yet because the shared
`CommonPhenoseeder.ice` and `PhytoCommon.ice` files are still required.

Ice is an optional dependency:

```powershell
python -m pip install -e ".[ice]"
```

## License

This project is licensed under the Apache License 2.0. See `LICENSE`.

The runtime dependencies are permissive, except for ZeroC Ice, which is
GPL-2.0-only with a ZeroC exception permitting combination with Apache-2.0
software. Ice is kept in an optional extra and should not be vendored into the
Apache-2.0 package. See `THIRD_PARTY_NOTICES.md` for details.

## Tests

```powershell
python -m pytest -q
```

The suite covers settings, stop policy, the fitting pipeline, the stored-point
regression fixture, single-image analysis, the session, and the folder source.
