# Files and Outputs

## Folder tree

```text
<calibration folder>/
├─ Calibration3DPositions.csv
├─ image_0001.tif
├─ image_0002.tif
├─ output/
│  ├─ CalibrationAllPoints.dat
│  ├─ calibration_data.yaml
│  └─ nozzle_uncertainty.json          # only when the optional bootstrap is enabled
└─ debug/
   ├─ result0000.png
   ├─ result0001.png
   ├─ ...
   └─ reporting plots
```

The names are controlled by `[general.files]` in the configuration. Older
documentation may refer to `all_points.dat`; the packaged default is
`CalibrationAllPoints.dat`.

## Ice session archive

When `archive_sessions = true` in `[general]`, each `init` call creates a date
folder below the selected procedure. If the procedure folder or its
`config.toml` does not exist, `init` creates it from the packaged default first.
The merged session config is stored beside the archive, and all
image/CSV/result files go directly into `data`:

```text
<procedures-root>/<procedure-id>/
├─ config.toml                         procedure default (auto-created)
├─ 20261103_1542/
│  ├─ config.toml                     merged config used for this session
│  └─ data/
│     ├─ Calibration3DPositions.csv
│     ├─ image_0001.tif
│     ├─ image_0002.tif
│     ├─ ...
│     ├─ calibration_result.yaml
│     └─ session.yaml
└─ 20261104_0810/
   ├─ config.toml
   └─ data/
      └─ ...
```

If another session starts in the same minute, `_01`, `_02`, ... is appended to
the date folder name. `init` returns the date folder, so a client can derive
`<returned>/config.toml` and `<returned>/data`.

`Calibration3DPositions.csv` uses the same semicolon-separated
`Xr;Yr;Zr;image_name` format as the folder workflow. The TIFF files keep the
dtype and bit depth of the frames received over Ice instead of rescaling wider
frames to 8 bit; boolean frames are stored as `uint8` because TIFF has no
boolean sample type. TIFF compression is set explicitly to Adobe Deflate.
Archived 8-bit and unsigned 16-bit data folders remain replayable with the
exact session config; wider or floating-point frames keep their precision for
later tooling:

```powershell
3dsc "<procedures-root>\1\20261103_1542\data" `
  --config "<procedures-root>\1\20261103_1542\config.toml"
```

`calibration_result.yaml` uses the same schema as the folder workflow's
`output/calibration_data.yaml`: `schema_version`, `nozzle`, and `camera` at the
top level, with the latest matrices, distortion coefficients, resolution, RMSE,
and observation counts under `camera`. It is updated whenever a fitted result is
available and is written atomically. The Ice archive has no nozzle measurement at
write time, so `nozzle.home_position` is `null`; `camera.errors` carries the
fitted one-sigma arrays in both workflows. `session.yaml` records the procedure
ID, the date/config/data paths, session start and end times, package version,
and image count.

## Point cache

`output/CalibrationAllPoints.dat` is a tab-separated table with one row per
analyzed image, including rejected rows. The file is replaced atomically, so a
failed run leaves the previous cache intact.

Header:

```text
Xr  Yr  Zr  Xc  Yc  radius  sigma border  image height  image width  nozzle_direction  center_cov_xx  center_cov_xy  center_cov_yy
```

| Column | Meaning |
| --- | --- |
| `Xr`, `Yr`, `Zr` | Robot coordinate in millimetres |
| `Xc`, `Yc` | Sphere centre in pixels |
| `radius` | Apparent radius in pixels |
| `sigma border` | Edge-blur standard deviation in pixels |
| `image height` | Image height in pixels |
| `image width` | Image width in pixels |
| `nozzle_direction` | `+1` top, `-1` bottom, `0` undefined |
| `center_cov_xx`, `center_cov_xy`, `center_cov_yy` | Symmetric 2×2 centre covariance in pixels² from the circle fit |

Invalid rows and radius outliers are stored as `NaN` in `radius`,
`sigma border`, and the covariance columns; centre coordinates are kept when
they were detected. On load, a row is valid only when all values are finite,
`radius > 0`, `sigma >= 0`, the image shape is positive, and the direction is
`±1`. The covariance columns are optional: caches written by older versions
contain only the first ten columns and load with `NaN` covariances, which
disables centre weighting for that cache.

Because the cache is already filtered, loading it disables the session's radius
filter. Use `--no-load-stored-data` to re-analyze images and regenerate it.

## Calibration result

`output/calibration_data.yaml`:

```yaml
schema_version: 1
nozzle:
  home_position:
  - 12.345
  - -40.123
  - 81.456
camera:
  model: pinhole
  resolution:
  - 2500
  - 2000
  intrinsic_matrix:
  - - 14788.04
    - 0.0
    - 1250.0
  - - 0.0
    - 14783.06
    - 1000.0
  - - 0.0
    - 0.0
    - 1.0
  extrinsic_matrix:
  - - r11
    - r12
    - r13
    - tx
  - - r21
    - r22
    - r23
    - ty
  - - r31
    - r32
    - r33
    - tz
  - - 0.0
    - 0.0
    - 0.0
    - 1.0
  distortion_coefficients:
  - k1
  - k2
  - p1
  - p2
  - 0.0
  - 0.0
  - 0.0
  - 0.0
  - 0.0
  - 0.0
  - 0.0
  - 0.0
  - 0.0
  - 0.0
  n_distortion_coefs: 4
  rmse: 0.2134
  observation_count: 500
  observations_used: 487
  sphere_home_position:
  - 15.2
  - -38.7
  - 80.9
  errors:
    intrinsic_std:
    - - 0.12
      - 0.0
      - 0.08
    - - 0.0
      - 0.13
      - 0.09
    - - 0.0
      - 0.0
      - 0.0
    rot_vec_std:
    - ...
    tra_vec_std:
    - ...
    distortion_std:
    - ...
  radial_scale:
    radii:
    - 0.0
    - 0.014
    - 0.028
    - 0.042
    - 0.056
    scale:
    - 1.0
    - 0.9999
    - 0.9995
    - 0.9987
    - 0.9965
```

Notes:

- `resolution` is `[width, height]`.
- Values with a one-sigma estimate — `intrinsic_matrix`, the translation column
  of `extrinsic_matrix`, `distortion_coefficients`, and every `errors` entry — are
  rounded to two significant digits of that uncertainty; each estimate uses the
  same decimal place as its error. `nozzle.home_position` is rounded to 1 µm
  (three decimals). Entries without an uncertainty keep full float precision:
  the rotation block of `extrinsic_matrix`, `sphere_home_position`, `rmse`, and
  `radial_scale`. Both workflows apply the same rule, and a value never keeps
  more than eight significant digits.
- `distortion_coefficients` always has 14 entries; inactive ones are zero.
- `radial_scale` reports the fitted radial distortion at the observed field
  rather than relying on the strongly correlated individual coefficients. The
  `radii` are ideal normalized image radii; `scale` is OpenCV's rational
  distorted/ideal factor at each radius. The profile is `1.0` for a pinhole fit.
  It is `null` when no inlier centres are available.
- `intrinsic_std[0][2]` and `[1][2]` are populated only when
  `fix_cx_cy = false`.
- Structurally fixed intrinsic entries, including `intrinsic_std[2][2]`, are
  `0.0`.
- `rot_vec_std` and `tra_vec_std` each contain three one-sigma values.
- `distortion_std` has 14 entries; inactive ones are zero.
- The example above uses four distortion coefficients; the packaged default is
  `n_distortion_coefs = 0`, so all distortion entries are zero.
- The numbers above are illustrative; use the values from your own run.
- Result YAML and `session.yaml` are written through a temporary file in the same
  folder and atomically replaced, so a crash cannot leave a truncated document.

## Nozzle uncertainty report

When `[analysis.uncertainty] enabled = true` (or `3dsc --bootstrap` is used), the
folder workflow writes `output/nozzle_uncertainty.json` after the main
calibration result. The sidecar keeps the main YAML schema stable.

It contains `schema_version`, `diagnostic`, the fitted observation counts and
RMSE, the sphere home and diameter, and the bootstrap summary:

```json
{
  "schema_version": 1,
  "diagnostic": "nozzle_home_residual_bootstrap",
  "fit": {"observation_count": 492, "observations_used": 482, "rmse": 4.32},
  "bootstrap_config": {"n_bootstrap": 500, "seed": 0},
  "nozzle_home_position": [315.4874, -111.521, -35.5721],
  "original": [315.4874, -111.521, -35.5721],
  "mean": [315.4881, -111.499, -35.5732],
  "bias": [0.0005, 0.023, -0.0008],
  "std": [0.0024, 0.061, 0.0055],
  "covariance": [[...], [...], [...]],
  "samples": [[...], ...],
  "lower_1sigma": [...],
  "upper_1sigma": [...]
}
```

The values are millimetres. The summary vectors (`original`, `mean`, `bias`,
`std`, the 1σ/2σ bounds, and the axis spreads) are rounded to two significant
digits of the bootstrap one-sigma; `samples` and `covariance` keep full
precision because they describe the replicate distribution. A failed optional
bootstrap prints a warning and does not invalidate the already stored
calibration.

## Per-image debug images

Written to `debug/` as `result####.png` (folder workflow) or `ice_####.png`
(Ice service):

- rejected images are written whenever a colour image is available;
- successful images are written only with `store_debug_images = true`;
- radius-outlier images are written when `debug = true`;
- a green circle marks the detected sphere when centre and radius are valid.

## Reporting plots

With `debug = true` the folder workflow calls `visualize_results` and writes:

| File | Content |
| --- | --- |
| `center_points_{n:02d}.png` | Image centres, `n` = effective distortion count |
| `radii_in_depth.png` | Apparent radius vs depth |
| `sigmas_in_depth.png` | Blur sigma vs depth |
| `scale_coef_estimation.png` | mm/px scale fit |
| `n_sigma_estimation.png` | Diameter consistency vs sigma correction |
| `sphere_diam_estimation.png` | Sphere-diameter estimate |
| `sphere_diam_vs_depth.png` | Diameter vs depth |
| `sphere_diam_rel_error_vs_depth.png` | Relative diameter error vs depth |
| `2D redidual vectors - N points.png` | Residual vectors (yes, the historical spelling is kept) |
| `focal length vs number of points.png` | Incremental `fx` stability |
| `focal length vs left number of points.png` | `fx` vs remaining points |
| `camera distance vs number of points.png` | Incremental `t_z` stability |
| `camera distance vs left number of points.png` | `t_z` vs remaining points |
| `RMSE vs number of points.png` | Incremental RMSE |

These plots are diagnostics only; the YAML file is the machine-readable result.

## Console output

With `debug = true` the CLI prints:

- per-fit progress (`N`, `t_z`, RMSE, parameters, remaining points);
- the sphere home and estimated diameter;
- the nozzle home;
- the closest image index;
- the full parameter table as `value +/- sigma`, rounded to two significant
  digits of the one-sigma;
- the back-projected home position.

Errors are printed with a traceback and re-raised, so the process exits non-zero.
