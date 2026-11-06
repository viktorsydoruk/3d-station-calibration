# 3D station calibration

Camera calibration for phenoSeeder 3D stations. A white sphere is moved through
the working volume; the images and matching robot positions are used to estimate
the camera intrinsics, distortion, the robot-to-camera transform, and the nozzle
home position.

Full documentation: [`docs/wiki/Home.md`](docs/wiki/Home.md).

## Install

The project uses a `src` layout. Install it in editable mode for development:

```powershell
python -m pip install -e .
```

or, with uv:

```powershell
uv sync
```

The package version is generated from Git tags, so there is no version string to
edit by hand. Check it with:

```powershell
3dsc --version
```

Create releases with `python scripts/release.py`; see
[Testing and Build](docs/wiki/Testing-and-Build.md#create-a-release). Release
notes are in [`CHANGELOG.md`](CHANGELOG.md).

## Run the folder workflow

```powershell
3dsc "P:\3Dcalibration\3D_example"
```

The equivalent module entry point is:

```powershell
python -m station_calibration "P:\3Dcalibration\3D_example"
```

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
<analysis folder>/output/CalibrationAllPoints.dat
<analysis folder>/output/calibration_data.yaml
<analysis folder>/debug/
```

`CalibrationAllPoints.dat` is the reusable per-image point cache. If it exists
and `load_stored_data` is enabled, the folder workflow can skip image analysis
and fit the cached observations directly.

## Architecture

```text
src/station_calibration/
├─ cli.py                 folder workflow entry point
├─ settings.py            TOML-backed settings
├─ models.py              observations, rejections, fit results
├─ session.py             source-agnostic incremental calibration session
├─ service.py             image-bytes/raw arrays -> analysis -> session service
├─ stop.py                readiness/stop policy
├─ vision/
│  ├─ models.py           image observation value objects
│  ├─ io.py               image loading/decoding
│  ├─ detection.py        sphere detection and blur estimation
│  ├─ debug.py            debug-image rendering
│  ├─ analysis.py         single-image and batch analysis
│  └─ geometry.py         image-point geometry helpers
├─ calibration/
│  ├─ initialization.py   initial rotation and parameter packing
│  ├─ model.py            camera model, projection, and unwrapping
│  ├─ fit.py              least-squares camera fit
│  └─ metrics.py          diagnostics, uncertainty, and reporting
├─ storage/
│  ├─ inputs.py           robot CSV and image discovery
│  ├─ points.py           point-cache serialization
│  └─ results.py          calibration-result YAML
├─ processes.py           iterative calibration pipeline
├─ robot.py               robot geometry and nozzle home estimation
├─ support.py             line geometry and parameter uncertainty
├─ plots.py               optional debug/reporting plots
├─ sources/
│  ├─ base.py             source/dataset protocols
│  └─ folder.py           folder source adapter
├─ ice/                   optional Ice adapter, server, client, generated stubs
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
# or, for a frontend that already provides a NumPy image:
service.add_image_array(image_array, robot_position)

if service.is_ready:
    result = service.finish()
```

`add_image_bytes` and `add_image_array` perform the same single-image analysis as
folder mode and feed the result into the shared session. Rejected images are
recorded but do not count toward the 500-observation readiness target. Readiness
is advisory: the session keeps accepting observations until the caller calls
`finish()` (or aborts).

## Ice frontend (optional)

The Ice frontend lives in `station_calibration.ice`. The production Slice
contracts are in `ice/`, including `CalibrationPhenoseederIcing.ice` and the
shared `CommonPhenoseeder.ice` and `PhytoCommon.ice` definitions; the older
`*_test.ice` files are retained only as a reference for the previous wire
layout. `addData` transports raw camera frames in `Phyto::Common::imageData`,
and the client decodes image files locally before sending them. Regenerate the
stubs with `scripts/generate_ice_stubs.py` after changing any `.ice` file.

Ice is an optional dependency:

```powershell
python -m pip install -e ".[ice]"
```

Start the server with its deployment config:

```powershell
3dsc-ice-server --config "C:\3DSC\config.toml"
```

The config must contain an absolute procedures root:

```toml
[general]
procedures_root = "C:/ProgramData/3DSC/procedures"
```

Use forward slashes or single-quoted TOML strings for Windows paths. A
double-quoted path with single backslashes fails with
`Unescaped '\' in a string`; see
[Configuration](docs/wiki/Configuration#windows-paths-in-toml).

If a procedure does not exist yet, `init` creates its folder and copies the
packaged default config, merging any optional override into that new procedure
default. The expected layout is:

```text
<procedures-root>/<procedure-id>/config.toml
<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/config.toml
<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/data/
```

The client starts a procedure with `init(procedureId[, configurationfilepath])`.
The optional config path must be absolute and on the server; it is recursively
merged over the procedure default. For an existing procedure, the override
applies only to that run. `init` returns the date folder, so the client can
derive `<returned>/config.toml` and `<returned>/data`. One server process is
sufficient when only one procedure is calibrated at a time. Switching away from
an unfinished procedure is rejected until the client calls `finish()` (force the
final result) or `abort()` (discard the live session).

The server receives images and robot positions over Ice; it does not read them
from the procedure folder. With `archive_sessions = true` (the default), each
session writes compressed TIFF frames at their source dtype and bit depth,
`Calibration3DPositions.csv`, `calibration_result.yaml`, and `session.yaml`
directly into `<date>/data`, so it can be re-analyzed with an updated fitting
procedure later.

See `ice/README.md` for generation details and the wire type layout, and
[`docs/wiki/Deployment.md`](docs/wiki/Deployment.md) for Windows/Raspberry Pi
installation, service autostart, and automatic updates.

Linux note: PyPI does not publish a Linux `zeroc-ice` wheel for 3.8.3. On
Debian/Ubuntu (including Raspberry Pi OS), install `python3-zeroc-ice` from the
official ZeroC APT repository and create the venv with
`--system-site-packages`; do not use the `[ice]` extra there.

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
regression fixture, single-image analysis, the session, the folder source, and
the optional Ice adapter/client when ZeroC Ice is installed.
