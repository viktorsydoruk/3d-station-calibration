# Folder Workflow

The folder workflow analyzes a directory that contains one calibration image per
robot position and writes the calibration result below that directory.

## Input layout

```text
<calibration folder>/
├─ Calibration3DPositions.csv
├─ image_0001.tif
├─ image_0002.tif
└─ ...
```

### Robot positions

`Calibration3DPositions.csv` is semicolon-separated:

```text
Xr;Yr;Zr;image_name
12.5;-40.0;81.2;image_0001.tif
12.5;-38.0;81.2;image_0002.tif
```

- The first three columns are the robot coordinates `Xr;Yr;Zr` in millimetres.
- The optional fourth column names the matching image.
- Rows whose first field contains the word `calibration` are skipped, so an
  informational header line is allowed.
- If no fourth column is present, images are discovered with
  `image_name_patterns` (default `*.tif`, `*.tiff`) and sorted by modification
  time when `sort_image_names_by_mtime = true`.

The number of robot positions must match the number of images; otherwise the
workflow raises:

```text
ValueError: The number of robot positions does not match the number of images: N vs M
```

### Images

Images are loaded with `cv2.IMREAD_UNCHANGED` and interpreted as follows:

| Shape | Interpretation |
| --- | --- |
| `(H, W)` | Raw Bayer frame, BG pattern |
| `(H, W, 3)` | BGR |
| `(H, W, 4)` | BGRA |

## Run

```powershell
3dsc "P:\3Dcalibration\3D_example"
```

Equivalent module entry point:

```powershell
python -m station_calibration "P:\3Dcalibration\3D_example"
```

### Options

| Option | Effect |
| --- | --- |
| `folder` | Calibration folder (required, positional) |
| `--config PATH` | Use this TOML file instead of the packaged default |
| `--debug` | Print detailed progress |
| `--store-debug-images` | Write per-image analysis images |
| `--load-stored-data` | Reuse `output/CalibrationAllPoints.dat` if it exists |
| `--no-load-stored-data` | Force re-analysis of the images |
| `--subpixel-edges` | Refine sphere edges to the sub-pixel 50 % crossing |
| `--no-subpixel-edges` | Force the binary mask edge even if the config enables refinement |
| `--target-observations N` | Override the readiness count floor (default 100) |
| `--max-observations N` | Set a hard readiness cap |
| `--bootstrap` | Write the optional post-fit nozzle-uncertainty report |
| `--no-bootstrap` | Disable the report even if the config enables it |
| `--bootstrap-n N` | Set the number of replicates; implies `--bootstrap` |
| `--bootstrap-seed N` | Set the random seed; implies `--bootstrap` |

Command-line values override the TOML file, and the TOML file overrides the
packaged defaults. See [Configuration](Configuration).

## Processing sequence

1. `Settings` resolves the folder, configuration, output folder, and debug
   folder.
2. `FolderCalibrationSource.load()` either loads the existing point cache or
   analyzes every image.
3. Each image goes through the single-image pipeline described in
   [Image Analysis](Image-Analysis). Rejected images are recorded with a reason
   and do not become observations.
4. Valid observations are fed **one at a time** into a single
   `CalibrationSession` with the configured `[analysis] fit_every_n` (default
   `5`). The session refits as data arrives once the minimum count is reached;
   `0` waits for the final `finish()`.
5. `session.finish()` guarantees a final fit that includes all observations.
6. The nozzle-end home position, sphere diameter, uncertainties, YAML result,
   and optional debug plots are produced.
7. If `[analysis.uncertainty] enabled = true` or `--bootstrap` is given, the
   residual-bootstrap nozzle report is written after the calibration result.

The folder workflow deliberately mirrors the incremental Ice workflow: the same
session, the same fit policy, and the same analysis code.

> **Note**
> The folder CLI does not stop early at `target_observations`; it feeds the whole
> dataset and then finishes. The stop policy is evaluated by the session and is
> primarily meaningful for incremental frontends. Use
> `--max-observations` only when a caller actually checks readiness between
> images.

## Cache reuse

After a fresh analysis the per-image data is written to:

```text
<folder>/output/CalibrationAllPoints.dat
```

If `load_stored_data = true` (the default) and that file exists, the next run
skips image analysis and feeds the cached observations directly. This is much
faster but reuses old sphere detections.

- Use `--no-load-stored-data` after changing analysis settings or images.
- The cache stores radius outliers as `NaN`; loading it marks those rows as
  invalid and the session does not apply the radius filter a second time.
- A freshly analyzed folder keeps the raw observations in the session and lets
  the session apply the radius filter, while the written cache already contains
  `NaN` for the filtered rows.

## Rejections

Typical rejection reasons:

- `direction is undefined` — neither the top nor the bottom band looks like
  background.
- `sphere is not found or out of FOV` — the sphere touches an image edge, the
  mask has a gap, or the circle fit failed.
- `border sigma cannot be estimated` — the edge profile or Gaussian fit failed.
- `invalid image analysis result` — non-finite values or an invalid direction.
- `stored point is invalid` — a cached row has `NaN`/non-positive radius or
  sigma, or an invalid image shape.

Rejected images are listed in `session.rejections`; they do not count toward
readiness or the observation count floor.

## Output summary

```text
<folder>/output/CalibrationAllPoints.dat
<folder>/output/calibration_data.yaml
<folder>/output/nozzle_uncertainty.json   # only when the optional bootstrap is enabled
<folder>/debug/...
```

See [Files and Outputs](Files-and-Outputs) for formats and plot names.
