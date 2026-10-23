# Ice interface

The wire contract remains at:

```text
_3dsc_resources/CalibrationPhenoseederIcing.ice
```

The shared production files `CommonPhenoseeder.ice` and `PhytoCommon.ice` are
not available in this checkout. This folder therefore contains local
compatibility definitions:

```text
CommonPhenoseeder.ice     CommonPhenoseeder::vecOfDoubles
PhytoCommon.ice           imageData, intrinsicParams, extrinsicParams
```

They are sufficient for a self-contained server/client pair and for end-to-end
testing. They are **not guaranteed to be wire-compatible** with the production
contracts on another machine. Before deploying against another machine, replace
these two files with the production definitions and regenerate the stubs.

The local definitions currently use these field layouts:

```text
Phyto::Common::imageData
    sequence<byte> data
    int width
    int height
    int channels

Phyto::Common::intrinsicParams
    double fx
    double fy
    double cx
    double cy

Phyto::Common::extrinsicParams
    CommonPhenoseeder::vecOfDoubles rotation   (row-major 3x3)
    CommonPhenoseeder::vecOfDoubles translation
```

## Generated stubs

Generated Python stubs live in:

```text
src/station_calibration/ice/generated/
```

Regenerate them after changing any `.ice` file:

```powershell
.\.venv\Scripts\python.exe ice\generate_stubs.py
```

The generated packages use absolute imports (`Phenoseeder`, `Phyto`,
`CommonPhenoseeder`). `station_calibration.ice._generated` adds the generated
directory to `sys.path` when the optional transport is used.

## Server

```powershell
.\.venv\Scripts\3dsc-ice-server.exe "P:\3Dcalibration\3D_20260824_2,3mm"
```

The server also accepts `--config`, `--endpoint`, and `--identity`. The image
folder is a deployment setting because it is not carried by the shared wire
contract. For clients on another machine, bind an externally reachable address,
for example `--endpoint "tcp -h 0.0.0.0 -p 10000"`.

The existing `init` operation accepts:

- `None`: use the server's startup folder and TOML configuration;
- a TOML file path: use that configuration with the server's folder;
- a directory path: use that folder as the calibration folder.

## Return conventions

- `getIntrinsic`: `fx`, `fy`, `cx`, `cy`; the error sequence uses the same order.
- `getExtrinsic`: row-major 3x3 rotation followed by the translation; the error
  sequence is `r1, r2, r3, t1, t2, t3`.
- `getDistortion`: only the active `n_distortion_coefs` values; the error
  sequence has the same length.
- `getOptimalNozzlePosition`: nozzle-end home position in robot coordinates,
  matching the folder workflow output.

## Client

The client is a small synchronous wrapper around the generated proxy:

```python
from station_calibration.ice import CalibrationIceClient

with CalibrationIceClient.connect() as client:
    client.init(None)
    client.add_image_file("image.tif", (x, y, z))
    if client.is_ready():
        intrinsic, intrinsic_error = client.get_intrinsic()
        extrinsic, extrinsic_error = client.get_extrinsic()
        distortion, distortion_error = client.get_distortion()
        nozzle = client.get_optimal_nozzle_position()
```

A one-image command-line client is also available:

```powershell
.\.venv\Scripts\3dsc-ice-client.exe --x 0 --y 0 --z 0 image.tif
```

Ice remains an optional dependency:

```powershell
python -m pip install -e ".[ice]"
```
