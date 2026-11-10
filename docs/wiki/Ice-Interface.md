# Ice Interface

The Ice frontend is optional and lives in `station_calibration.ice`. It exposes
the same calibration engine through a `CalibrationPhenoseederIcing` servant.

> **Contract source**
> `ice/CommonPhenoseeder.ice` and `ice/PhytoCommon.ice` now contain the shared
> production definitions. The `*_test.ice` files preserve the previous local
> compatibility shims for reference only. `ice/PhytoError.ice` is an empty
> placeholder for the include used by `PhytoCommon.ice`; the calibration
> contract does not use any Phyto error type.

## Contract

```text
ice/CalibrationPhenoseederIcing.ice
```

Operations:

| Operation | Direction | Purpose |
| --- | --- | --- |
| `calibrate(...)` | legacy | Retained by the contract; returns an empty list |
| `init(int procedureId, optional string configurationfilepath)` | client → server | Start a procedure session and return its date folder |
| `addData(Point, imageData)` | client → server | Analyze one image and add the observation |
| `isReady()` | client → server | Readiness flag |
| `getIntrinsic()` | client → server | 3×3 matrix + 9 errors |
| `getExtrinsic()` | client → server | Rotation, translation + 6 errors |
| `getDistortion()` | client → server | Active coefficients + errors |
| `getOptimalNozzlePosition()` | client → server | Nozzle-end home in robot coordinates |
| `abort()` | client → server | Abort the active calibration and discard its in-memory state |
| `finish()` | client → server | Force a final fit; return `true` when a result is available |

`isReady()` becomes true only after the configured count floor is reached and the
fitted camera parameters have stopped changing materially. It does not wait for
nozzle-position uncertainty. Explicit and maximum-observation stops force
readiness so the operator can always finish a session.

### Wire type layout

```text
Phyto::Common::imageData
    long timeNbr
    int height
    int width
    int spp
    IMAGEFORMAT imgformat
    IMAGEDATATYPE imgDataType
    int cameraId
    cameraParams virtualCamParams
    boolVec boolPixels
    byteVec bytePixels
    shortVec shortPixels
    floatVec floatPixels

Phyto::Common::intrinsicParams
    INTRINSICMODEL modelId
    doubleVec modelParams

Phyto::Common::extrinsicParams
    EXTRINSICMODEL modelId
    BOOLFLAG isAbsolute
    COORDINATESYSTEM coordsys
    int coordSysIndex
    doubleVec modelParams
```

`imageData` is a raw camera-frame container. Exactly one pixel vector is
populated, normally `bytePixels`. The adapter selects it, reshapes it with
`height`/`width`/`spp`, and calls `CalibrationService.add_image_array()`. The
client decodes image files locally and fills the same fields. The conversion
helpers live in `station_calibration.ice.images`.

## Generated stubs

```text
src/station_calibration/ice/generated/
```

Regenerate after any `.ice` change:

```powershell
.\.venv\Scripts\python.exe scripts\generate_ice_stubs.py
```

The script finds `slice2py` next to the interpreter or on `PATH`, removes the
previous generated packages, compiles the shared includes plus the contract into
the generated directory, and keeps the result under version control.
`station_calibration.ice._generated` adds that directory to `sys.path` so the
absolute imports (`Phenoseeder`, `Phyto`, `CommonPhenoseeder`) resolve.

## Server

```powershell
uv sync --extra ice
3dsc-ice-server --config "C:\3DSC\config.toml"
```

| Option | Default |
| --- | --- |
| `--config` | required |
| `--endpoint` | `tcp -h 127.0.0.1 -p 10000` |
| `--identity` | `CalibrationPhenoseederIcing` |

The config must contain an absolute procedures root:

```toml
[general]
# Local archive
procedures_root = "C:/ProgramData/3DSC/procedures"

# Network archive alternative; single quotes keep backslashes literal
# procedures_root = '\\server\share\3DSC\procedures'
```

Use single quotes or forward slashes in TOML for Windows paths; a double-quoted
path with single backslashes fails with `Unescaped '\' in a string`. See
[Windows paths in TOML](Configuration#windows-paths-in-toml).

If the root is a UNC path, set absolute local `output_folder` and `debug_folder`
paths in the procedure config to keep output and debug data off the share. See
[Deployment and Autostart](Deployment#network-archive-with-local-output-and-debug).

Each procedure has a complete default at
`<procedures-root>/<procedure-id>/config.toml`. If it is missing, `init` creates
the procedure folder and copies the packaged default there. `init` also creates
`<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/` with a merged `config.toml`
and a `data` folder.

The servant starts uninitialized. Before `init`, `isReady()` and `finish()`
return `false`, `abort()` is a no-op, and the data/getter operations raise a
clear `RuntimeError`. Once initialized, the
servant constructs a `CalibrationService` with the procedure's configured
`[analysis] fit_every_n`, `apply_radius_filter=True`, and
`load_stored_data=False`, so the server always analyzes newly arriving images.
`fit_every_n=0` disables intermediate fits until `finish()`.

### `init` semantics

| Argument | Effect |
| --- | --- |
| `procedureId` | Select `<procedures-root>/<str(procedureId)>/config.toml`, creating the procedure folder/config from the packaged default if needed |
| `configurationfilepath` | Optional absolute server-side TOML recursively merged over the procedure default |

Path-valued keys in a client override (`output_folder`, `debug_folder`,
`robot_pos_filename`, and `all_center_points_filename`) must stay relative and
may not contain `..`. Absolute paths remain valid in the server-owned procedure
default, but a remote client cannot use an override to redirect session writes
outside `<date>/data`.

The folder name is exactly `str(procedureId)`, with no zero padding. If the
optional path is relative or missing, `init` raises. For a new procedure, the
override is merged into the new persistent procedure default. For an existing
procedure, the override applies only to the current run. The merged result is
always a complete config and is written to `<date>/config.toml`; the archive
writes to `<date>/data`.

The date folder format is `YYYYMMDD_HHMM`. If a session already exists for that
minute, `_01`, `_02`, ... is appended. `init` returns the absolute date folder so
the client can derive `<returned>/config.toml` and `<returned>/data`.

Every accepted `init` creates a fresh settings object, service, and archive
session, clearing the nozzle and error caches.

A new `init` (for the same or a different procedure) is rejected with an Ice
exception while the current session has received images and has not been
finished. Readiness alone is not enough: the client must call `finish()` to keep
the result or `abort()` to discard the live session, then call `init` again.
Retrieve the results before finishing if needed; the archive remains on disk.

### `finish` and `abort`

| Operation | Behavior |
| --- | --- |
| `finish()` | Force a final fit with all currently valid observations, ignoring the `target_observations` stop condition. Returns `true` when a result is available and `false` when no result can be produced. Writes `calibration_result.yaml` using the shared result schema; `nozzle.home_position` is `null` because the Ice archive has no nozzle measurement, while `camera.errors` carries the fitted one-sigma arrays. A successful finish also makes `isReady()` return `true`. |
| `abort()` | Close the active archive and discard the live service, settings, and session state. Archived images and results stay on disk. Before `init`, `abort()` is a no-op. |

> To verify a new server build, call these operations only while no session is
> active. Before `init()`, `finish()` returns `false` and `abort()` is a no-op.
> On an active session they finalize or discard it.

Adding data after a successful `finish()` reopens the session: `isReady()` falls
back to the normal stop policy until `finish()` is called again. Re-selecting the
same procedure after `finish()` or `abort()` starts a new date folder; without
one of those calls it is rejected.

### Thread safety and caching

The servant serializes operations with an `RLock`. It caches:

- calibration errors for the current `CalibrationResult`;
- the nozzle position keyed by result identity, observation count, and used
  count.

`_current_result()` calls `finish_if_ready()` when the session is ready,
otherwise it returns the last result. If neither exists, the getters raise
`RuntimeError`.

## Client

```python
from station_calibration.ice import CalibrationIceClient

with CalibrationIceClient.connect("CalibrationPhenoseederIcing:tcp -h 127.0.0.1 -p 10000") as client:
    session_folder = client.init(1)
    client.add_image_file("image.tif", (x, y, z))

    if client.finish():
        intrinsic, intrinsic_error = client.get_intrinsic()
        extrinsic, extrinsic_error = client.get_extrinsic()
        distortion, distortion_error = client.get_distortion()
        nozzle = client.get_optimal_nozzle_position()

    client.abort()
```

`connect()` creates and owns a communicator; `close()` or the context manager
destroys it. It sets `--Ice.MessageSizeMax=65536` by default, matching the server,
so full-resolution raw frames do not hit Ice's 1 MB incoming-message limit. Pass
`message_size_max_kb=` to override it. `add_image()` accepts a NumPy frame or
encoded bytes; encoded bytes are decoded locally because the wire contract
carries raw pixels. `add_image_file()` reads and decodes the file before sending.

### Client CLI

```powershell
3dsc-ice-client --procedure-id 1 --x 12.5 --y -40.0 --z 81.2 image.tif
```

| Option | Meaning |
| --- | --- |
| `--proxy` | Proxy string, default `CalibrationPhenoseederIcing:tcp -h 127.0.0.1 -p 10000` |
| `--procedure-id` | Integer procedure ID passed to `init` |
| `--config` | Optional absolute server-side TOML merged with the procedure default |
| `image` | Encoded image file |
| `--x`, `--y`, `--z` | Robot coordinate |

The CLI prints the returned session folder, readiness, and, when ready, the
matrices, errors, distortion, and nozzle position.

## Return conventions

| Getter | Value | Error sequence |
| --- | --- | --- |
| `getIntrinsic` | `INTRINSICMATRIX`; `modelParams` = full 3×3 row-major matrix | 9 row-major one-sigma values; structurally fixed entries are `0` |
| `getExtrinsic` | `EXTRINSICROTMATRIX`; `modelParams` = `Tx, Ty, Tz` then row-major rotation | `r1, r2, r3, t1, t2, t3` |
| `getDistortion` | First `n_distortion_coefs` values | Same length |
| `getOptimalNozzlePosition` | Nozzle-end home in robot coordinates | — |

The nozzle result matches the folder workflow's
`get_nozzle_end_home_position` output.

## Deployment

For a client on another machine, bind an externally reachable address:

```powershell
3dsc-ice-server `
  --config "C:\3DSC\config.toml" `
  --endpoint "tcp -h 0.0.0.0 -p 10000"
```

Check the firewall for the chosen port and use the printed `Proxy:` line on the
client. Prefer a private network or an Ice configuration with authentication for
production. Full Windows service and Raspberry Pi systemd instructions are in
[Deployment and Autostart](Deployment).

## Contract maintenance

1. Update `ice/CalibrationPhenoseederIcing.ice`, `ice/CommonPhenoseeder.ice`, or
   `ice/PhytoCommon.ice`.
2. Update `station_calibration.ice.images` and the adapter/client when the
   `imageData` or camera-parameter fields change.
3. Regenerate the stubs with `scripts/generate_ice_stubs.py`.
4. Update `tests/test_ice_adapter.py` and run a real cross-machine exchange.
5. Rebuild the wheel/sdist and verify the packaged stubs.
