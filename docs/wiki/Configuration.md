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
| `debug` | `false` | Print detailed progress and write reporting plots |
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
| `max_outliers` | `10` | Outlier policy, see below (must be ≥ 0) |
| `outlier_confidence` | `0.999` | Confidence level of the 2D chi-square outlier test (must be in `(0, 1)`) |
| `outlier_cluster_guard` | `true` | Keep high-score candidates that form a compact spatial cluster |
| `fit_every_n` | `5` | Refit after this many new valid observations; `0` disables intermediate fits and waits for `finish()` (must be ≥ 0) |

The first automatic fit is not delayed by `fit_every_n`: it runs as soon as
enough observations survive radius filtering. Later refits use the configured
cadence.

`max_outliers` (Python: `allowed_outliers`):

- `0` — no outlier-removal iterations, one fit pass.
- `0 < x < 1` — at most `int(N * x)` removals, minimum one iteration.
- `x >= 1` — at most `int(x)` removals.
- Iterations are capped at `N - min_points + 1` so that enough points remain.

The removal decision itself uses a leverage-corrected 2D Mahalanobis score and
a chi-square threshold; see
[Calibration model · Outlier test](Calibration-Model.md#outlier-test).
`outlier_confidence` controls that threshold. `outlier_cluster_guard` keeps a
compact group of high-score points instead of removing it, because such a group
usually reflects a systematic robot or camera-model effect rather than isolated
blunders.

`fit_every_n` controls how often a running session refits while observations are
still arriving. The final `finish()` call always performs a fit, so larger values
reduce CPU use during long acquisitions without changing the final result. The
folder workflow and the Ice server both read this setting.

## `[analysis.background]`

| Key | Default | Meaning |
| --- | --- | --- |
| `fixed_bg_threshold` | `30` | Fixed intensity threshold; `0` enables automatic estimation |
| `bg_height_pxs` | `200` | Height of the background band at the top/bottom |
| `bg_threshold_method` | `"percentile"` | Automatic method: `"percentile"` or `"mad"` |
| `bg_noise_sigma` | `5.0` | Robust noise multiplier for the opt-in `"mad"` method |
| `bg_color_est_perc` | `99.999` | Percentile of the band for the `"percentile"` method |

`bg_height_pxs` must be at least 10 because the background estimator starts at
row 10. Numeric settings must be finite; `NaN` and infinity are rejected during
configuration loading.

`bg_threshold_method = "mad"` takes the larger of `median + bg_noise_sigma *
1.4826 * MAD` and the `bg_color_est_perc` percentile over the quietest
background rows. `bg_noise_sigma` must be positive; larger values reject more
background noise but require a brighter sphere. It is opt-in because quantized
8-bit backgrounds often have `MAD = 0`; the percentile floor keeps the result
at or above the legacy threshold in that case. The default `"percentile"` uses
`bg_color_est_perc` directly (must be in `(0, 100]`). Raise the percentile when
the background contains bright reflections; lower it when the sphere is dim.
Configurations written before this key existed fall back to `"percentile"`.

## `[analysis.sphere_projection]`

| Key | Default | Meaning |
| --- | --- | --- |
| `n_move_aver` | `11` | Moving-average width for the rough sphere-centre search |
| `sphere_center_to_nozzle_part` | `0.7` | Fraction of the sphere used on the nozzle side |
| `min_bg_pixels_on_edges` | `5` | Required background margin around the sphere |
| `blur_est_border_thickness` | `2` | Annular border thickness for the blur profile |
| `subpixel_edges` | `false` | Move the silhouette edge to the 50 % intensity crossing |
| `subpixel_max_n_sigma` | `0.25` | Cap on the sub-pixel radius-vs-blur correction |

Ranges: `n_move_aver >= 1`, `0 <= sphere_center_to_nozzle_part <= 1`,
`min_bg_pixels_on_edges >= 1`, `blur_est_border_thickness >= 1`,
`subpixel_max_n_sigma >= 0` when set.

`subpixel_edges = true` refines the sphere silhouette to the 50 % intensity
crossing between the local background and the sphere interior. The binary mask
supplies the rough circle; the refinement samples radial profiles around the
sphere, estimates a local background and interior level on each ray, and trims
inconsistent crossings before the final circle fit. The radial search window is
blur-aware from the first attempt: it is the largest of `0.2 * radius`,
`3 * sigma`, and `1.5 * 0.2 * radius`, capped at half the binary radius. A fixed
20 % window can truncate the inner edge plateau and bias the crossing outward on
defocused spheres. If the profiles still do not resolve the edge transition, or
the outer/inner plateaus are not flat, the search retries once at the half-radius
cap; if the crossings remain unreliable, the binary circle is retained.
`edge_search_px` on `find_the_sphere_on_mask` is an explicit override and
disables both the blur-aware choice and the retry.

Because the binary mask threshold sits near the background level, its contour lies
roughly `~1 sigma` outside the true silhouette; the offset grows with defocus.
The sub-pixel path removes most of that radius bias. On the well-focused real
2 mm and 6 mm sets the empirical blur correction dropped to `0`, the
scan-to-scan diameter spread of the 6 mm sphere fell from `0.013 mm` to
`0.005 mm`, and the calibration RMSE changed by about `0.2 px`; the centre
moves by only a few tenths of a pixel. On strongly defocused spheres the
correction is partial. The radius-outlier filter uses the binary-mask radius as
a method-independent reference when `subpixel_edges = true`, so the smaller
sub-pixel mean does not create extra high-radius rejections; the sub-pixel
radius still feeds the fit. See [Image Analysis](Image-Analysis) for the broad
black-background validation.

`subpixel_max_n_sigma` caps the empirical `n_sigma` term when
`subpixel_edges = true`. The raw 50 % crossing already removes most of the
binary threshold bias; an overly wide search window used to leave a strong
residual radius-vs-blur trend and a large empirical correction. Across the
full broad A/B run the adaptive `n_sigma_opt` was `0.000-0.162`, so the
`0.25 sigma` cap never bound. With the
blur-aware first window, the full 1 mm ceramic run chose `n_sigma_opt = 0.040`
and reported `0.9962 mm`; the `0.25 sigma` cap was not binding, and the
equivalent continuous bootstrap interval was `[0.004, 0.064]` (grid
`[0, 0.081]`). At zero empirical correction the adaptive diameter was
`0.9985 mm`, so the residual correction is only a `2.3 um` adjustment. The
binary production fit on the same folder reported `0.9949 mm`. A micrometer
measurement of the ceramic balls gives `0.998-1.000 mm` (midpoint
`0.999 mm`), so the uncorrected adaptive result is within `0.5 um`, the
corrected adaptive result is about `2.8 um` low, and the binary result is
about `4.1 um` low. The cap changes only the final sphere radius and nozzle
offset, not the camera fit or RMSE. Keep the cap as a guardrail against a
pathological dataset; do not tune it to hit a nominal diameter.

## `[analysis.fit]`

| Key | Default | Meaning |
| --- | --- | --- |
| `fix_cx_cy` | `true` | Fix the principal point at the image centre |
| `n_distortion_coefs` | `0` | Number of active OpenCV distortion coefficients |
| `focal_length_initial` | `2000.0` | Initial `fx`/`fy` in pixels |
| `camera_distance_initial` | `80.0` | Initial translation `t_z` in millimetres |
| `loss_f_scale` | `5.0` | Pixel scale where the `soft_l1` robust loss starts downweighting residuals; must be positive and finite |
| `center_weighting` | `true` | Use the per-image circle-fit centre covariance as measurement weights |

`center_weighting` turns the camera fit into a generalized least-squares fit:
each measured image centre is whitened by the 2×2 covariance estimated by the
circle fit. It adds one initial unweighted fit to calibrate the global residual
scale; image analysis is unaffected. Caches written before covariance support
contain no covariance columns; they fall back to an unweighted fit until the
images are re-analyzed with `--no-load-stored-data`.

`n_distortion_coefs` must be one of `0, 4, 5, 8, 12, 14`:

| Count | Active coefficients |
| --- | --- |
| `0` | none |
| `4` | `k1, k2, p1, p2` |
| `5` | `k1, k2, p1, p2, k3` |
| `8` | `k1, k2, p1, p2, k3, k4, k5, k6` |
| `12` | + `s1, s2, s3, s4` |
| `14` | + `τx, τy` |

The minimum observation count is `10 + n_distortion_coefs`, so the default `0`
requires at least 10 observations.

When `fix_cx_cy = true`, `cx` and `cy` are set to `width / 2` and
`height / 2`. Set it to `false` to estimate the principal point; that parameter
is weakly constrained by a small or poorly distributed dataset.

## `[analysis.stop]`

| Key | Default | Meaning |
| --- | --- | --- |
| `target_observations` | `100` | Minimum count before saturation-based readiness is evaluated |
| `max_observations` | unset | Optional safety cap; reaching it forces readiness |

Both values must be positive. If either is smaller than `min_observations`
(`10 + n_distortion_coefs`), session construction raises `ValueError`.

Reaching `target_observations` is necessary but not sufficient when
`[analysis.readiness] enabled = true`: the fitted camera parameters must also
have stopped changing materially. More observations are accepted while the fit
is still moving.

## `[analysis.readiness]`

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Layer the saturation test on top of the count floor |
| `checkpoint_interval` | `10` | Record a fit checkpoint after this many new valid observations |
| `stable_checkpoints` | `3` | Compare the mean of the last N checkpoints with the previous N |
| `min_inlier_fraction` | `0.9` | Minimum fraction of observations that must survive filtering |
| `focal_relative_tolerance` | `0.001` | Maximum relative change in `fx`/`fy` |
| `principal_point_tolerance_px` | `0.05` | Maximum change in `cx`/`cy` in pixels |
| `translation_tolerance_mm` | `0.05` | Maximum translation change in millimetres |
| `rotation_tolerance_deg` | `0.01` | Maximum rotation change in degrees |
| `home_tolerance_mm` | `0.05` | Maximum change in fitted sphere home position |
| `distortion_tolerance` | `0.0001` | Maximum absolute change in active distortion coefficients |

Readiness asks whether more images would materially change the calibration. It
does not use nozzle-position error or nozzle uncertainty. Setting `enabled =
false` restores count-only readiness. Count-only readiness is also used
automatically when automatic fitting is disabled (`fit_every_n = 0`), because
there are no incremental fit checkpoints to compare.

`checkpoint_interval`, `stable_checkpoints`, and all tolerances must be
positive. `min_inlier_fraction` must be in `(0, 1]`.

## `[analysis.uncertainty]`

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | Run the optional post-fit nozzle-home bootstrap |
| `n_bootstrap` | `500` | Number of bootstrap replicates; must be positive |
| `seed` | `0` | Random seed; must be non-negative |
| `report_filename` | `nozzle_uncertainty.json` | Sidecar JSON file inside the output folder |

This diagnostic reruns the camera fit and nozzle-home estimator for every
replicate. It is separate from the calibration result and does not affect the
readiness gate. Enable it from the configuration or with `3dsc --bootstrap`;
`--bootstrap-n` and `--bootstrap-seed` override the replicate count and seed and
imply `--bootstrap` unless `--no-bootstrap` is given.

Because the diagnostic conditions on the original inlier set and keeps robot
positions fixed, it reports measurement-noise uncertainty rather than robot or
model error. See [Home and Nozzle](Home-and-Nozzle#nozzle-home-uncertainty).

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
outlier_confidence = 0.999
outlier_cluster_guard = true

[analysis.background]
fixed_bg_threshold = 0
bg_height_pxs = 250
bg_threshold_method = "percentile"
bg_color_est_perc = 99.99

[analysis.sphere_projection]
sphere_center_to_nozzle_part = 0.65

[analysis.fit]
fix_cx_cy = true
n_distortion_coefs = 5

[analysis.stop]
target_observations = 100
max_observations = 500

[analysis.readiness]
enabled = true
checkpoint_interval = 10
stable_checkpoints = 3

[analysis.uncertainty]
enabled = true
n_bootstrap = 500
seed = 0
report_filename = "nozzle_uncertainty.json"
```

## Validation errors

| Error | Cause |
| --- | --- |
| `FileNotFoundError` | Config file does not exist |
| `ValueError: Unknown settings: ...` | Unknown keyword argument to `Settings` |
| `KeyError: Missing config section '[...]'` | A required TOML table is absent |
| `KeyError: Missing required setting '...'` | A required key is absent |
| `ValueError` | A numeric range check failed (for example a bad distortion count) |
