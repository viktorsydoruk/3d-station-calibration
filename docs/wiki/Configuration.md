# Configuration

Settings come from three layers, highest priority last:

1. the packaged default `src/station_calibration/resources/config.toml`,
2. an optional TOML file passed with `--config` or `config_file=...`,
3. keyword arguments to `Settings(...)`.

Most CLI flags are thin wrappers around the keyword arguments. Values that are
`None` are treated as “not overridden”, so `Settings` falls back to the TOML
value.

> **Current implementation:** the `--config` file is loaded by `Settings` as a
> complete replacement, not merged key-by-key with the packaged default. Copy
> the packaged `config.toml` and edit the copy; a partial runtime config is
> rejected with a missing-section error. The Ice server itself only reads
> `[general] procedures_root` from `--config`. Each Ice procedure has a complete
> default at `<procedures-root>/<procedure-id>/config.toml`. If it is missing,
> `init` creates the procedure folder and copies the packaged default there. The
> optional `init` override is recursively merged over that procedure default; for
> a newly created procedure it becomes part of the new procedure default, while
> for an existing procedure it applies only to the current run. The merged copy
> is written to `<date>/config.toml`. `[general] procedures_root` is server-only;
> it is ignored when the file is used as a procedure config.

## Path resolution

- Relative paths in `[general.files]` are resolved against the calibration
  folder. Absolute paths are used as-is, so absolute `output_folder` and
  `debug_folder` values stay on the local disk when the calibration folder is on
  a network share.
- `output_folder` and `debug_folder` are created when `Settings` is constructed.
- `all_center_points_filename` is resolved inside the output folder.
- `config_file` is expanded with `~` but is otherwise used as given.

### Windows paths in TOML

TOML basic strings (`"..."`) process backslash escapes. A Windows path such as
`C:\3DSC\procedures` contains `\3`, which is not a valid escape, so the file fails
to parse:

```text
tomllib.TOMLDecodeError: Unescaped '\' in a string (at line 20, column 22)
```

Use a literal string, double every backslash, or use forward slashes:

```toml
# Literal string: backslashes are not escapes (recommended)
procedures_root = '\\server\share\3DSC\procedures'
output_folder = 'C:\ProgramData\3DSC\output'

# Basic string: every backslash must be doubled
procedures_root = "\\\\server\\share\\3DSC\\procedures"
output_folder = "C:\\ProgramData\\3DSC\\output"

# Forward slashes also work on Windows
procedures_root = "//server/share/3DSC/procedures"
output_folder = "C:/ProgramData/3DSC/output"
```

A UNC path starts with two backslashes, so its basic-string form starts with
four. Single-quoted literal strings cannot contain a single quote; use a basic
string if a path does.

## `[general]`

| Key | Default | Meaning |
| --- | --- | --- |
| `debug` | `true` | Print detailed progress and write reporting plots |
| `store_debug_images` | `false` | Also write a debug image for successful analyses |
| `archive_sessions` | `true` | Archive each Ice session's images, robot positions, and latest result in `<date>/data` |
| `load_stored_data` | `true` | Reuse the point cache when it exists |
| `procedures_root` | `""` | Absolute folder containing per-procedure folders for the Ice server; required by `3dsc-ice-server` and ignored by the folder workflow |

## `[general.files]`

| Key | Default | Meaning |
| --- | --- | --- |
| `robot_pos_filename` | `Calibration3DPositions.csv` | Robot-position CSV |
| `output_folder` | `output` | Result folder, relative to the calibration folder; absolute paths are used as-is |
| `debug_folder` | `debug` | Debug-image folder, relative to the calibration folder; absolute paths are used as-is |
| `all_center_points_filename` | `CalibrationAllPoints.dat` | Point-cache file inside the output folder |
| `image_name_patterns` | `["*.tif", "*.tiff"]` | Glob patterns used when the CSV has no image names |
| `sort_image_names_by_mtime` | `true` | Sort discovered images by modification time |

Python attribute aliases differ where the TOML name is more descriptive:

| TOML key | `Settings` attribute / kwarg |
| --- | --- |
| `robot_pos_filename` | `robot_pos_file` |
| `all_center_points_filename` | `all_center_points_file` |
| `sort_image_names_by_mtime` | `sort_imagenames_by_mtime` |

## `[analysis]`

| Key | Default | Meaning |
| --- | --- | --- |
| `n_iterations` | `3` | Inner camera/home/centre adjustment iterations (must be ≥ 1) |
| `max_outliers` | `0` | Outlier policy, see below (must be ≥ 0) |

`max_outliers` (Python: `allowed_outliers`):

- `0` — no outlier-removal iterations, one fit pass.
- `0 < x < 1` — at most `int(N * x)` removals, minimum one iteration.
- `x >= 1` — at most `int(x)` removals.
- Iterations are capped at `N - min_points + 1` so that enough points remain.

## `[analysis.background]`

| Key | Default | Meaning |
| --- | --- | --- |
| `fixed_bg_threshold` | `30` | Fixed intensity threshold; `0` enables automatic estimation |
| `bg_height_pxs` | `200` | Height of the background band at the top/bottom |
| `bg_color_est_perc` | `99.999` | Percentile of the band used as the threshold |

`bg_height_pxs` must be at least 1 in `Settings`; the analysis path additionally
requires at least 10 rows because the background estimator starts at row 10.
`bg_color_est_perc` must be in `(0, 100]`. Raise the percentile when the
background contains bright reflections; lower it when the sphere is dim.

## `[analysis.sphere_projection]`

| Key | Default | Meaning |
| --- | --- | --- |
| `n_move_aver` | `11` | Moving-average width for the rough sphere-centre search |
| `sphere_center_to_nozzle_part` | `0.7` | Fraction of the sphere used on the nozzle side |
| `min_bg_pixels_on_edges` | `5` | Required background margin around the sphere |
| `blur_est_border_thickness` | `2` | Annular border thickness for the blur profile |

Ranges: `n_move_aver >= 1`, `0 <= sphere_center_to_nozzle_part <= 1`,
`min_bg_pixels_on_edges >= 1`, `blur_est_border_thickness >= 1`.

## `[analysis.fit]`

| Key | Default | Meaning |
| --- | --- | --- |
| `fix_cx_cy` | `true` | Fix the principal point at the image centre |
| `n_distortion_coefs` | `4` | Number of active OpenCV distortion coefficients |
| `focal_length_initial` | `2000.0` | Initial `fx`/`fy` in pixels |
| `camera_distance_initial` | `80.0` | Initial translation `t_z` in millimetres |

`n_distortion_coefs` must be one of `0, 4, 5, 8, 12, 14`:

| Count | Active coefficients |
| --- | --- |
| `0` | none |
| `4` | `k1, k2, p1, p2` |
| `5` | `k1, k2, p1, p2, k3` |
| `8` | `k1, k2, p1, p2, k3, k4, k5, k6` |
| `12` | + `s1, s2, s3, s4` |
| `14` | + `τx, τy` |

The minimum observation count is `10 + n_distortion_coefs`, so the default `4`
requires at least 14 observations.

When `fix_cx_cy = true`, `cx` and `cy` are set to `width / 2` and
`height / 2`. Set it to `false` to estimate the principal point; that parameter
is weakly constrained by a small or poorly distributed dataset.

## `[analysis.stop]`

| Key | Default | Meaning |
| --- | --- | --- |
| `target_observations` | `500` | Readiness target for valid observations |
| `max_observations` | unset | Optional earlier readiness threshold |

Both values must be positive. If either is smaller than `min_observations`
(`10 + n_distortion_coefs`), session construction raises `ValueError`.

## Example

```toml
[general]
debug = false
store_debug_images = true
load_stored_data = false

[general.files]
robot_pos_filename = "positions.csv"
output_folder = "results"
debug_folder = "diagnostics"

[analysis]
n_iterations = 4
max_outliers = 0.02

[analysis.background]
fixed_bg_threshold = 0
bg_height_pxs = 250
bg_color_est_perc = 99.99

[analysis.sphere_projection]
sphere_center_to_nozzle_part = 0.65

[analysis.fit]
fix_cx_cy = true
n_distortion_coefs = 5

[analysis.stop]
target_observations = 400
max_observations = 500
```

## Validation errors

| Error | Cause |
| --- | --- |
| `FileNotFoundError` | Config file does not exist |
| `ValueError: Unknown settings: ...` | Unknown keyword argument to `Settings` |
| `KeyError: Missing config section '[...]'` | A required TOML table is absent |
| `KeyError: Missing required setting '...'` | A required key is absent |
| `ValueError` | A numeric range check failed (for example a bad distortion count) |
