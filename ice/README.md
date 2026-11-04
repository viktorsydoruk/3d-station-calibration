# Ice interface

All production Slice contracts live in this folder:

```text
CalibrationPhenoseederIcing.ice  calibration wire contract
CommonPhenoseeder.ice            shared CommonPhenoseeder module
PhytoCommon.ice                  Phyto::Common camera and image types
PhytoError.ice                   placeholder for the include used by PhytoCommon.ice
```

The `*_test.ice` files are the previous local compatibility shims, kept only as
a reference for the old wire layout. `scripts/generate_ice_stubs.py` uses the
production files without the `_test` suffix.

`PhytoCommon.ice` includes `PhytoError.ice`. The calibration contract does not
reference any Phyto error type, so `ice/PhytoError.ice` contains an empty
`Phyto::Error` module. Replace it with the production file if error types ever
become part of the wire contract.

## Wire types

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

`addData` transports a **raw camera frame**, not an encoded image file. Exactly
one pixel vector is populated, normally `bytePixels`. The servant selects that
vector, reshapes it with `height`, `width`, and `spp`, and calls
`CalibrationService.add_image_array()`. The client decodes image files locally
and fills the same fields.

## Generated stubs

Generated Python stubs live in:

```text
src/station_calibration/ice/generated/
```

Regenerate them after changing any `.ice` file:

```powershell
.\.venv\Scripts\python.exe scripts\generate_ice_stubs.py
```

The script removes the generated `Phenoseeder`, `Phyto`, and
`CommonPhenoseeder` packages before compiling, so renamed or removed Slice
definitions do not leave stale stubs behind.

The generated packages use absolute imports (`Phenoseeder`, `Phyto`,
`CommonPhenoseeder`). `station_calibration.ice._generated` adds the generated
directory to `sys.path` when the optional transport is used.

## Server

```powershell
.\.venv\Scripts\3dsc-ice-server.exe --config "C:\3DSC\config.toml"
```

The config is required and must contain an absolute procedures root:

```toml
[general]
procedures_root = "C:/ProgramData/3DSC/procedures"
```

The server also accepts `--endpoint` and `--identity`. For clients on another
machine, bind an externally reachable address, for example
`--endpoint "tcp -h 0.0.0.0 -p 10000"`.

Each procedure has a complete default configuration at
`<procedures-root>/<procedure-id>/config.toml`. `init` creates
`<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/` with a merged `config.toml`
and a `data` folder, then returns the date folder.

```text
init(int procedureId, optional(1) string configurationfilepath) -> string
```

`configurationfilepath` is optional and must be an absolute path on the server.
Its tables are recursively merged over the procedure default; scalars and arrays
replace the default value. The date folder name uses `_01`, `_02`, ... for
same-minute collisions.

## Return conventions

- `getIntrinsic`: `modelId = INTRINSICMATRIX`; `modelParams` is the full 3x3
  matrix in row-major order. The error sequence contains nine row-major
  one-sigma values, with zero for structurally fixed entries.
- `getExtrinsic`: `modelId = EXTRINSICROTMATRIX`; `modelParams` is
  `Tx, Ty, Tz` followed by the row-major 3x3 rotation, as required by the shared
  contract. The error sequence is `r1, r2, r3, t1, t2, t3`.
- `getDistortion`: only the active `n_distortion_coefs` values; the error
  sequence has the same length.
- `getOptimalNozzlePosition`: nozzle-end home position in robot coordinates,
  matching the folder workflow output.

## Client

The client is a small synchronous wrapper around the generated proxy:

```python
from station_calibration.ice import CalibrationIceClient

with CalibrationIceClient.connect() as client:
    session_folder = client.init(1)
    client.add_image_file("image.tif", (x, y, z))
    if client.is_ready():
        intrinsic, intrinsic_error = client.get_intrinsic()
        extrinsic, extrinsic_error = client.get_extrinsic()
        distortion, distortion_error = client.get_distortion()
        nozzle = client.get_optimal_nozzle_position()
```

`add_image()` accepts either a NumPy frame or encoded image bytes. Encoded bytes
are decoded locally because the shared contract transports raw pixels.
`add_image_file()` reads and decodes the file before sending.

A one-image command-line client is also available:

```powershell
.\.venv\Scripts\3dsc-ice-client.exe --procedure-id 1 --x 0 --y 0 --z 0 image.tif
```

Ice remains an optional dependency:

```powershell
python -m pip install -e ".[ice]"
```
