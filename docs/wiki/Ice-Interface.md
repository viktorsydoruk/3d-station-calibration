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
_3dsc_resources/CalibrationPhenoseederIcing.ice
```

Operations:

| Operation | Direction | Purpose |
| --- | --- | --- |
| `calibrate(...)` | legacy | Retained by the contract; returns an empty list |
| `init(optional string path)` | client → server | Reset the session from a TOML file, folder, or `None` |
| `addData(Point, imageData)` | client → server | Analyze one image and add the observation |
| `isReady()` | client → server | Readiness flag |
| `getIntrinsic()` | client → server | 3×3 matrix + 9 errors |
| `getExtrinsic()` | client → server | Rotation, translation + 6 errors |
| `getDistortion()` | client → server | Active coefficients + errors |
| `getOptimalNozzlePosition()` | client → server | Nozzle-end home in robot coordinates |

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
.\.venv\Scripts\python.exe ice\generate_stubs.py
```

The script finds `slice2py` next to the interpreter or on `PATH`, removes the
previous generated packages, compiles the shared includes plus the contract into
the generated directory, and keeps the result under version control.
`station_calibration.ice._generated` adds that directory to `sys.path` so the
absolute imports (`Phenoseeder`, `Phyto`, `CommonPhenoseeder`) resolve.

## Server

```powershell
uv sync --extra ice
3dsc-ice-server "P:\3Dcalibration\3D_example"
```

| Option | Default |
| --- | --- |
| `folder` | required |
| `--config` | packaged config |
| `--endpoint` | `tcp -h 127.0.0.1 -p 10000` |
| `--identity` | `CalibrationPhenoseederIcing` |

At startup the servant constructs a `CalibrationService` with
`fit_every_n=1`, `apply_radius_filter=True`, and `load_stored_data=False`, so the
server always analyzes newly arriving images.

### `init` semantics

| Argument | Effect |
| --- | --- |
| `None` | Keep the server's startup folder and config |
| Directory path | Use that folder as the calibration folder |
| TOML file path | Use that configuration with the server's folder |

Every `init` creates a fresh settings object and a fresh service, clearing the
nozzle and error caches.

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
    client.init(None)
    client.add_image_file("image.tif", (x, y, z))

    if client.is_ready():
        intrinsic, intrinsic_error = client.get_intrinsic()
        extrinsic, extrinsic_error = client.get_extrinsic()
        distortion, distortion_error = client.get_distortion()
        nozzle = client.get_optimal_nozzle_position()
```

`connect()` creates and owns a communicator; `close()` or the context manager
destroys it. `add_image()` accepts a NumPy frame or encoded bytes; encoded bytes
are decoded locally because the wire contract carries raw pixels.
`add_image_file()` reads and decodes the file before sending.

### Client CLI

```powershell
3dsc-ice-client --x 12.5 --y -40.0 --z 81.2 image.tif
```

| Option | Meaning |
| --- | --- |
| `--proxy` | Proxy string, default `CalibrationPhenoseederIcing:tcp -h 127.0.0.1 -p 10000` |
| `--config` | Optional TOML file or calibration folder passed to `init` |
| `image` | Encoded image file |
| `--x`, `--y`, `--z` | Robot coordinate |

The CLI prints readiness and, when ready, the matrices, errors, distortion,
and nozzle position.

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
3dsc-ice-server "\\server\share\3Dcalibration\run_001" `
  --endpoint "tcp -h 0.0.0.0 -p 10000"
```

Check the firewall for the chosen port and use the printed `Proxy:` line on the
client. Prefer a private network or an Ice configuration with authentication for
production. Full Windows service and Raspberry Pi systemd instructions are in
[Deployment and Autostart](Deployment).

## Contract maintenance

1. Update `ice/CommonPhenoseeder.ice`, `ice/PhytoCommon.ice`, or the contract in
   `_3dsc_resources/`.
2. Update `station_calibration.ice.images` and the adapter/client when the
   `imageData` or camera-parameter fields change.
3. Regenerate the stubs with `ice/generate_stubs.py`.
4. Update `tests/test_ice_adapter.py` and run a real cross-machine exchange.
5. Rebuild the wheel/sdist and verify the packaged stubs.
