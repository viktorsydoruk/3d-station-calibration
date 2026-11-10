# Image Analysis

Every image is reduced to four numbers plus a direction:

```text
x, y      sphere centre in pixels
radius    apparent sphere radius in pixels
sigma     edge-blur standard deviation in pixels
direction +1 (nozzle at the top) or -1 (nozzle at the bottom)
```

## Entry points

| Function | Input |
| --- | --- |
| `analyze_image(gray, color)` | Already decoded arrays |
| `analyze_image_array(array)` | Raw Bayer/BGR/BGRA NumPy array |
| `analyze_image_bytes(bytes)` | Encoded TIFF/PNG bytes |
| `analyze_images(paths)` | Files on disk, one `ImageAnalysisResult` each |
| `get_sphere_centers_and_blur_sigmas(paths)` | Legacy array-oriented batch helper |

`analyze_image` never touches the filesystem. Optional debug images are written
only when a target path and a colour image are supplied.

The batch helpers keep one result per input path. A corrupt, missing, or
unsupported frame is recorded as a rejection with its filename position intact
instead of aborting the whole folder. Debug rendering never mutates the caller's
image array, so read-only Ice frames are safe.

## Pipeline

### 1. Decode and split

`split_image` converts the input into a gray and a colour variant:

| Input | Gray conversion | Colour conversion |
| --- | --- | --- |
| 2D Bayer | `COLOR_BAYER_BG2GRAY` | `COLOR_BAYER_BG2BGR` |
| 3-channel BGR | `COLOR_BGR2GRAY` | unchanged |
| 4-channel BGRA | `COLOR_BGRA2GRAY` | `COLOR_BGRA2BGR` |

Anything else raises `ValueError`.

### 2. Nozzle direction

`estimate_direction` compares the standard deviation of the bottom and top image
bands (`bg_height_px // 2` rows each):

- bottom clearly quieter → `+1`, nozzle comes from the top;
- top clearly quieter → `-1`, nozzle comes from the bottom;
- otherwise → `0`, and the image is rejected.

The rule is `1.5 * quieter_std < noisier_std`. The background band is quieter
because it contains only the empty conveyor/background. The two bands are kept
disjoint: on a frame shorter than twice the requested band, each side uses
`image_height // 2` rows so a real asymmetry is not hidden by sampling the same
pixels twice.

### 3. Background threshold

If `fixed_bg_threshold != 0`, that value is used directly. Otherwise the
threshold is estimated from the quietest background prefix:

1. Take a band of at most `bg_height_px` rows from the background side
   (bottom for `direction = +1`, top for `direction = -1`).
2. Compute the cumulative standard deviation for prefixes of at least 10 rows.
3. Choose the prefix length with the smallest standard deviation. This avoids
   rows that contain the sphere or nozzle.
4. Turn the prefix into a threshold with `bg_threshold_method`:
   - `"percentile"` (default): the `bg_color_est_perc` percentile of the
     prefix. 99.999 % tolerates a few bright outlier pixels.
   - `"mad"` (opt-in): the larger of `median + bg_noise_sigma * 1.4826 *
     MAD` and the `bg_color_est_perc` percentile. The multiplier is an
     explicit confidence level in units of robust noise and does not drift
     with the number of pixels. The percentile is a lower bound, so this mode
     never goes below the legacy threshold.

The MAD estimate is robust to hot pixels and specular highlights, but on
quantized 8-bit backgrounds more than half of the pixels can equal the median.
`MAD` then collapses to zero; without the percentile floor the threshold would
fall back to the median and turn the sensor pattern into foreground. On the
available real calibration data the pure MAD estimate rejected most frames for
this reason, so `"mad"` is not the default and is always floored. Keep
`bg_threshold_method = "percentile"` unless you have verified the mode on your
camera. The implementation uses prefix sums rather than a Python loop over
pixels. A threshold below the darkest pixel or at/above the brightest pixel is
rejected before the sphere search; see [Rejections](#rejections).

### 4. Foreground mask

`get_forground_mask`:

1. threshold `gray > threshold`,
2. apply a 3×3 elliptical morphological opening,
3. keep the largest external contour,
4. fill that contour.

This removes small bright islands and leaves one connected foreground blob
containing the nozzle and the sphere.

### 5. Sphere detection

`find_the_sphere_on_mask` works on row statistics:

1. Count foreground pixels per row.
2. For `direction = +1`, find the lowest foreground row `y_e`; for `-1`, the
   highest row `y_0`.
3. Smooth the row counts with `n_move_aver` and locate the rough equator.
4. Extend from the equator toward the nozzle by
   `sphere_center_to_nozzle_part` × the opposite cap height. This keeps most of
   the sphere but stops short of the nozzle/gripper, whose silhouette would
   bias the circle fit.
5. Reject if the sphere touches the image border within
   `min_bg_pixels_on_edges` pixels, or if a row in the band has no foreground
   pixel.
6. Collect the left and right boundary pixel of every row in the band.
7. Fit a circle to those boundary points in the least-squares sense.

The result is `(x_c, y_c, radius)`, or `None`.

### Sub-pixel edge refinement (opt-in)

Passing `subpixel_edges=True` to `analyze_image`, `analyze_images`, or
`get_sphere_centers_and_blur_sigmas`, or setting `subpixel_edges = true` in
`[analysis.sphere_projection]`, refines the sphere silhouette to the
**50 % intensity crossing** between the local background and the sphere
interior. The binary mask still supplies the rough circle and the radius scale
for the blur-aware search window. The refinement then samples 360 radial
profiles and locates the crossing on each ray by linear interpolation. Because every ray crosses the
edge normally, the noisy, nearly horizontal top and bottom rows of a row-wise
scan no longer contribute. Each ray estimates its own background and interior
level, which handles a smooth illumination gradient; rays on the nozzle side
are skipped with the same `sphere_center_to_nozzle_part` rule as the binary
fit, and a MAD-based trim drops inconsistent crossings before the final circle
fit.

The reason is the radius bias: the mask threshold sits near the background
level, so the integer contour lies roughly `~1 sigma` outside the true
silhouette. That offset grows with defocus and is invisible to a centre-only
check. On synthetic blurred spheres the sub-pixel path removes it (for example,
a radius error of `+5.7 px` at `sigma = 5 px` becomes about `-0.1 px`) without
changing the centre accuracy. On a real 2 mm sphere set (124 poses, 8 mm depth
range) the empirical blur correction `n_sigma_est` drops from `0.69 sigma` to
`0`, and the radius consistency at zero correction improves from `0.027 mm` to
`0.008 mm`. On two independent 6 mm sphere scans the adaptive diameter becomes
more repeatable (`5.972` / `5.966 mm` versus `5.969` / `5.982 mm`), while the
calibration RMSE changes by `+0.12` and `+0.01 px`.

#### Broad validation (black backgrounds)

The blur-aware search was validated in a full A/B run over 11 calibration
folders and 4,184 source frames. No frames were sampled. An image was included
only when the darker of its 200-row top/bottom background bands had a median
below 25 DN (the fixed detection threshold is 30 DN); this selected 3,684
frames. `3D_small20260914random` has a gray background and contributed no
selected frames. The same selected-image subset was analyzed in both modes and
fed to the complete calibration fit. The accuracy-scan folders have degenerate
calibration geometry and were excluded from the fit comparison;
`3D_small_20260929_POM` fails in both modes with a non-positive focal length.

Detection parity was essentially exact: 3,373 binary and 3,374 adaptive
detections; 3,373 frames were detected by both, with one sub-pixel-only frame
(`3D_oldsmallseeds`) and no binary-only frames. On the 3,373 common frames the
adaptive radius moved inward by `7.05 px` on average, or `0.75 sigma` per
frame; this is the expected binary-threshold bias. The shift reached about
`-11 px` on the strongly defocused old-small set and `-3` to `-5 px` on the
well-focused 2 mm and 6 mm sets.

In the table, `sigma` is the folder-mean binary blur, the binary diameter uses
the production uncapped `n_sigma` correction, and the adaptive diameter uses
the `0.25 sigma` cap. The cap never bound on the adaptive path: the largest
`n_sigma_opt` was `0.162`, so the adaptive capped and uncapped diameters are
identical.

| Dataset | `sigma` (px) | Binary dia. (mm) | Adaptive dia. (mm) | Binary RMSE (px) | Adaptive RMSE (px) | `n_sigma_opt` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 mm A | 2.9 | 5.9691 | 5.9720 | 1.052 | 1.174 | 0.000 |
| 6 mm B | 3.4 | 5.9822 | 5.9661 | 1.247 | 1.259 | 0.000 |
| 2 mm | 5.0 | 1.9849 | 1.9573 | 1.428 | 1.469 | 0.000 |
| 2.3 mm A | 5.7 | 2.3660 | 2.3543 | 1.201 | 1.415 | 0.000 |
| 2.3 mm B | 5.1 | 2.3677 | 2.3564 | 1.203 | 1.283 | 0.000 |
| small random A | 10.2 | 0.9527 | 0.9575 | 4.752 | 4.714 | 0.000 |
| small random B | 10.4 | 0.9832 | 0.9845 | 4.473 | 4.254 | 0.081 |
| old small A | 30.5 | 1.0331 | 0.9922 | 2.693 | 2.522 | 0.121 |
| old small B | 10.7 | 0.9851 | 0.9906 | 2.728 | 2.665 | 0.162 |
| ceramic | 10.0 | 0.9949 | 0.9962 | 4.555 | 4.538 | 0.040 |

Adaptive RMSE was lower on 5 of 10 folders, with a median change of
`-0.002 px` and a range from `-0.219` to `+0.214 px`. It was worse on the
2 mm and both 2.3 mm scans by `0.04-0.21 px`, and better on both small-random,
both old-small, and ceramic sets. The 6 mm A/B RMSE asymmetry remains: the
adaptive path does not remove the `+0.12 px` change on 6 mm A or the
`5.966/5.972 mm` absolute offset from the 6 mm nominal. The same-sphere
scan-to-scan spread improves for the 6 mm pair (`0.0130 -> 0.0059 mm`), small
random pair (`0.0305 -> 0.0270 mm`), and old small pair
(`0.0480 -> 0.0017 mm`); the 2.3 mm pair was already consistent
(`0.0017 -> 0.0021 mm`). The 6 mm asymmetry is therefore not explained by the
search window alone.

The fixed `0.2 * radius` window was the dominant source of the residual
radius-vs-sigma trend. On the same 489 ceramic frames and the same 479 fit
observations, the old window gave `n_sigma_opt = 0.485`, a capped diameter of
`0.9921 mm`, and `RMSE = 4.2729 px`; the blur-aware window gave
`n_sigma_opt = 0.040`, `0.9960 mm`, and `4.2562 px`. At zero empirical
correction the adaptive diameter is `0.9983 mm`. The current window starts at
`max(0.2 * radius, 3 * sigma, 1.5 * 0.2 * radius)`, is capped at half the binary
radius, retries once at the cap, and honours an explicit `edge_search_px`
override. If too few rays pass, or the fitted circle is biased enough to make
the border-sigma fit fail, the binary circle is retained.

The raw 50 % crossing is not the only bias: the residual `n_sigma` correction
is still dataset-dependent, although it is now small on the well-focused sets.
On the full 1 mm ceramic run the binary production result is `0.9949 mm`, the
adaptive result is `0.9962 mm`, and the zero-correction adaptive result is
`0.9985 mm`. A micrometer measured the two ceramic balls several times at
`0.998`, `0.999`, and `1.000 mm` with `1 um` resolution; the exact ball used in
the dataset is not recorded, but the full range is only `2 um`, so the
reference midpoint is `0.999 +/- 0.001 mm`. Relative to that midpoint the
adaptive result is about `2.8 um` low, the zero-correction adaptive result is
about `0.5 um` low, and the binary result is about `4.1 um` low. The older
fixed-window capped result (`0.9921 mm`, `6.9 um` low) and the old uncapped
result (`0.9782 mm`, `20.8 um` low) are superseded. The exact ball identity
and the micrometer calibration record remain open metrology items.

A percentile bootstrap of the adaptive `n_sigma_opt` scan on the full ceramic
production run (489 fit observations, 4,000 replicates, seed 0) gave a grid
interval of `[0, 0.081]` and a continuous interval of `[0.004, 0.064]` around a
continuous optimum of `0.033`; the grid point estimate was `0.040`. The interval is
conditional on the fitted scale model and the selected inliers and excludes
systematic edge-extraction, illumination, reflectivity, and sphere-diameter
errors. It does not justify tuning the cap or the correction to reproduce the
micrometer value.

#### Sub-pixel radius-correction cap

With the blur-aware search, the sub-pixel `n_sigma_opt` was `0.000-0.162`
across the broad folders, so the `0.25 sigma` cap never bound and the cap
changes neither the camera fit nor RMSE. On the full ceramic set the residual
correction is only `2.3 um` of diameter; the raw result is already within the
micrometer range. Keep `subpixel_max_n_sigma = 0.25` as a guardrail against a
pathological dataset, but do not lower it to force a nominal diameter. The cap
is not a statistical estimate of the observed optimum and should be revisited
only with a larger traceable reference set.

The evidence for the sub-pixel path is the reduced blur-dependent radius
spread, the improved repeatability of the 6 mm, small-random, and old-small
pairs, and the removal of the search-window artefact. It is not a universal
RMSE improvement: the 2 mm and 2.3 mm fits became slightly worse. The packaged
default therefore remains `false`; enable it per station after checking a
black-background calibration run, a reference-sphere diameter, the radius-vs-
sigma trend, and the bootstrap interval.

### 6. Edge blur (`sigma`)

`get_blur_sigma` estimates defocus from the intensity profile across the sphere
edge:

1. Crop a square around the sphere.
2. For ring widths `i = border_thickness ... radius/2`, build the annulus
   between radius `r - i` and `r - i + border_thickness`.
3. Take the mean intensity in each annulus, cut away the nozzle-side part, and
   differentiate along the radius.
4. Fit a Gaussian to the derivative; its standard deviation is `sigma`.

`sigma` is used by the home-shift and nozzle estimators, not as a residual
weight in the camera fit. The stored value is the raw edge-profile estimate;
those estimators add `SIGMA_OFFSET = 0.5 px` before use so a zero sigma remains
numerically safe.

## Rejections

`ImageAnalysisResult` always carries the image shape and direction. When no
observation is produced it also carries a reason:

| Reason | Trigger |
| --- | --- |
| `direction is undefined` | Top and bottom bands look equally busy |
| `background threshold is outside the usable range` | Threshold is below the darkest pixel or at/above the brightest pixel |
| `sphere is not found or out of FOV` | Border margin, gap in the mask, or failed circle fit |
| `border sigma cannot be estimated` | Edge profile or Gaussian fit failed |
| `invalid image analysis result` | Non-finite/invalid values after analysis |

Rejections are stored separately and never count toward readiness. Their image
size is still considered when the session determines the camera resolution.

## Radius outlier filter

`get_radius_outlier_mask` flags a radius when

```text
|radius - nanmean(radius)| > 2.5 * nanstd(radius)
```

and the sigma is not `NaN`. The filter is applied by `CalibrationSession` at fit
time. Folder analysis writes `NaN` for the filtered rows in the point cache; a
cache loaded later already has those rows removed, so the session disables the
filter for stored data.

## Debug images

- Rejected images are written as `debug/result####.png` whenever a colour image
  is available, even when `store_debug_images` is `false`. A circle is drawn
  only if a valid centre/radius was available.
- Successful images are written only with `store_debug_images = true`.
- Radius-filtered images are written when `debug = true`.
- The Ice service uses `debug/ice_####.png`.
- Additional reporting plots are written when `debug = true`; see
  [Files and Outputs](Files-and-Outputs).

## Tuning

| Symptom | Parameter to adjust |
| --- | --- |
| Sphere merges with the nozzle | Decrease `sphere_center_to_nozzle_part` |
| Sphere touches the border | Increase `min_bg_pixels_on_edges` or move the sphere |
| Background threshold too low/high | Set `fixed_bg_threshold`, tune `bg_noise_sigma`, or switch `bg_threshold_method` / tune `bg_color_est_perc` |
| Rough centre unstable | Increase `n_move_aver` |
| Noisy sigma | Increase `blur_est_border_thickness` |

### Background diagnostics

With `debug = true`, every frame prints a `BG_stats` line next to `BG_thr`:

```text
BG_stats: median=17.0, MAD=0.00, p99.999=19.0, thr=19.0, rows=10, fg=3.42%
```

`rows` is the selected quietest-prefix length and `fg` is the foreground
fraction of the final mask. A very small `rows` value with a stable threshold
is harmless; a threshold close to the image maximum or a large `fg` points to a
background-estimation problem rather than a missing sphere.

### Real-data regression

`scripts/background_regression.py` samples the accepted dark-background
folders and compares `"percentile"`, floored `"mad"`, and the fixed 30 DN
reference. It reports success counts, threshold and radius stability, paired
centre/radius differences, and the accuracy residuals after linear trend
removal. It needs the laboratory data and is intentionally not part of the test
suite:

```bash
uv run python scripts/background_regression.py --samples 60
uv run python scripts/background_regression.py --dataset accuracy_test_x --csv bg.csv
```

## Performance

The hot paths are vectorized:

- background prefix selection via cumulative sums over the band;
- row extents via `np.minimum.at` / `np.maximum.at`.

The blur estimate only touches the cropped square around the detected sphere;
the full image is used for the mask and the background estimate.
