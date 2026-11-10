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
because it contains only the empty conveyor/background.

### 3. Background threshold

If `fixed_bg_threshold != 0`, that value is used directly. Otherwise
`get_bg_value` estimates it:

1. Take a band of at most `bg_height_px` rows from the background side
   (bottom for `direction = +1`, top for `direction = -1`).
2. Compute the cumulative standard deviation for prefixes of at least 10 rows.
3. Choose the prefix length with the smallest standard deviation. This avoids
   rows that contain the sphere or nozzle.
4. Return the `bg_color_est_perc` percentile of that prefix.

The default 99.999 % percentile tolerates a few bright outlier pixels. The
implementation uses prefix sums rather than a Python loop over pixels.

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
interior. The binary mask still supplies the rough circle and the search
window. The refinement then samples 360 radial profiles and locates the
crossing on each ray by linear interpolation. Because every ray crosses the
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
a radius error of `+5.7 px` at `sigma = 5 px` becomes about `-0.05 px`) without
changing the centre accuracy. On a real 2 mm sphere set (124 poses, 8 mm depth
range) the empirical blur correction `n_sigma_est` drops from `0.69 sigma` to
`0`, and the radius consistency at zero correction improves from `0.027 mm` to
`0.006 mm`. On two independent 6 mm sphere scans the estimated diameter becomes
more repeatable (`5.972` / `5.977 mm` versus `5.982` / `5.969 mm`), while the
calibration RMSE changes between `-0.20 px` and `+0.06 px`.

#### Broad validation (black backgrounds)

A wider A/B run covered 14 calibration folders and 2,307 frames whose darker
200-row background band had a median below 25 DN (the fixed detection threshold
is 30 DN). Folders with a gray (~30 DN) or bright (~163 DN) background were
excluded. Detection parity was essentially exact: 2,166 binary vs 2,165
sub-pixel detections; only `3D_oldsmallseeds` contributed two binary-only and
one sub-pixel-only frame.

On 692 well-focused observations (folder-mean `sigma` 2.9–5.7 px) the sub-pixel
radius moved inward by `4.17 px` on average; the mean per-frame correction was
`0.85 sigma`.
On the 6 mm high-contrast set the fixed 30 DN threshold sits at 12–13 % of the
local edge range; a Gaussian edge predicts a 2.6–4.3 px outward bias, and the
measured shift was 2.6–4.4 px. This is direct evidence that the refinement
reaches the 50 % crossing.

In the table, `radius_std@0` is the radius standard deviation at zero blur
correction. The sub-pixel columns show the uncapped optimum; the
`subpixel_max_n_sigma` cap described below changes the sub-pixel diameter but
not the camera fit or RMSE.

| Dataset | `sigma` (px) | `n_sigma_est` | `radius_std@0` (mm) | Diameter (mm) | RMSE (px) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 6 mm A | 2.9 | 1.09 → 0.00 | 0.0104 → 0.0043 | 5.9691 → 5.9772 | 1.052 → 1.062 |
| 6 mm B | 3.4 | 0.77 → 0.00 | 0.0152 → 0.0063 | 5.9822 → 5.9724 | 1.247 → 1.043 |
| 2 mm | 5.0 | 0.69 → 0.00 | 0.0274 → 0.0057 | 1.9849 → 1.9706 | 1.428 → 1.484 |
| 2.3 mm A | 5.7 | 0.73 → 0.04 | 0.0401 → 0.0053 | 2.3660 → 2.3583 | 1.201 → 1.274 |
| 2.3 mm B | 5.1 | 0.73 → 0.00 | 0.0397 → 0.0047 | 2.3678 → 2.3633 | 1.123 → 1.309 |
| small random A | 10.2 | 0.85 → 0.57 | 0.0341 → 0.0192 | 0.9529 → 0.9376 | 4.265 → 4.326 |
| small random B | 10.1 | 0.89 → 0.65 | 0.0342 → 0.0208 | 0.9835 → 0.9626 | 3.732 → 3.570 |
| ceramic | 9.8 | 0.97 → 0.61 | 0.0384 → 0.0208 | 0.9925 → 0.9753 | 4.370 → 3.679 |
| old small A | 31.0 | 0.28 → 0.28 | 0.0649 → 0.0675 | 1.0331 → 1.0123 | 2.693 → 2.657 |
| old small B | 10.8 | 0.81 → 0.69 | 0.0282 → 0.0220 | 0.9851 → 0.9667 | 2.753 → 2.704 |

The same-sphere scan-to-scan diameter spread improves for the 6 mm sphere
(`0.0131 mm` → `0.0048 mm`), the small random pair (`0.0306` → `0.0250 mm`),
and the old small pair (`0.0480` → `0.0456 mm`). The 2.3 mm pair was already
very consistent with the binary mask (`0.0018 mm`) and remains within
`0.0050 mm` with sub-pixel edges; both are within about 0.2 %. RMSE changes are
mixed and small (typically less than `0.3 px`, up to `0.7 px` on the blurriest
sets).

The blur correction is partial for strongly defocused spheres
(folder-mean `sigma` 9.8–31 px: mean per-frame correction `0.59 sigma`) and
unreliable for extreme-defocus frames (`sigma` 70–120 px), where the
`0.2 * radius` search window no longer spans the edge transition.

Before the reference filter, the radius filter flagged 22 binary
vs 37 sub-pixel observations across the broad run, with the extra cases
concentrated on small spheres. The extra points were high-radius frames, not
depth-related (`corr(radius, z)` is approximately zero), and are likely
nozzle/edge contamination. Because the filter uses an absolute `2.5 sigma`
threshold, a method with a smaller mean radius rejected the same relative
deviation more often. The filter now uses the binary-mask radius as a
method-independent reference when sub-pixel edges are enabled; the sub-pixel
radius still feeds the fit. On the full ceramic folder this restored the binary
fit-observation count (`489` vs `481` before) and brought the camera fit and
RMSE close to the binary result (`4.551` vs `4.555 px`).

The absolute diameter shifts by `-0.72 %` on the 2 mm set, `-0.26 %` on the
2.3 mm set, and roughly `-2 %` on the smallest spheres. Without a traceable
reference diameter these cannot be called corrections; the producer's nominal
diameter is a sanity check, not a metrology-grade reference.

A full 500-image run of the 1 mm ceramic folder
(`3D_small_20260929_ceramic`) gave 489 used observations and `0.9949 mm` with
the binary mask versus 489 used observations and `0.9968 mm` with sub-pixel
edges and the `0.25 sigma` cap. The uncapped sub-pixel result at the same
observations is `0.9727 mm`. The producer
quotes a 1 mm nominal diameter, but the measurement method and tolerance are
not available. The binary result is 0.51 % low, the capped sub-pixel result
0.32 % low, and the uncapped result 2.73 % low. The `0.0223 mm`
binary-uncapped difference is about 2.1 sigma of the bootstrap along-axis
uncertainty (`0.0106 mm`); the capped difference is well inside it, so this is
an indicative check rather than proof. On the same run the sub-pixel fit had a
slightly lower RMSE (`4.551` vs `4.555 px`) with the same observation count;
its `n_sigma_est` was `0.65` (capped at `0.25`), while the best corrected
radius scatter was `0.0096 mm` versus `0.0047 mm` for the binary mask.

#### Sub-pixel radius-correction cap

The sub-pixel 50 % crossing removes most of the binary threshold bias, but the
remaining empirical `n_sigma` correction can overcorrect the absolute diameter.
The full 1 mm ceramic run is the clearest case: the raw sub-pixel diameter is
`1.0120 mm`, the uncapped fit chooses `0.65 sigma` and reports `0.9727 mm`, and
a `0.25 sigma` cap reports `0.9968 mm` (binary `0.9949 mm`). The camera fit and
RMSE are unchanged by the cap; only the final sphere radius and nozzle offset
change. The cap also increases the corrected radius scatter from `0.0096` to
`0.0155 mm`, still between the uncapped sub-pixel value and the binary
`0.0047 mm`.

The cap was re-checked on sampled small-sphere folders (165–180 frames each)
with the complete fitting procedure and the binary-reference radius filter:

| Dataset | Binary dia. (mm) | Sub-pixel uncapped (mm) | Sub-pixel capped (mm) |
| --- | ---: | ---: | ---: |
| small random A | 0.9529 | 0.9378 | 0.9569 |
| small random B | 0.9835 | 0.9628 | 0.9873 |
| old small B | 0.9851 | 0.9667 | 0.9959 |
| ceramic (full) | 0.9949 | 0.9727 | 0.9968 |

The cap moves the sub-pixel diameters toward the binary results and, where a
1 mm nominal applies, close to the nominal value. It does not make the
sub-pixel path more accurate than the binary mask on every folder, and the
nominal diameter is not traceable; the cap is a correction for the known
overcorrection, not evidence that sub-pixel edges should become the default.

The evidence for the sub-pixel path is therefore still the reduced
blur-dependent radius spread and the improved 6 mm repeatability, not the
absolute diameter. The accuracy-scan folders have degenerate calibration
geometry and were used only for detection comparison;
`3D_small_20260929_POM` fails in both modes with a negative focal length.

The packaged default remains `false`. The cap removes the largest known
overcorrection when sub-pixel edges are enabled, and the reference radius filter
now keeps the same observations as the binary mask on the full ceramic folder,
but the extreme-defocus search window remains open and the absolute diameter
still lacks a traceable reference. Enable it per station after checking the
radius and diameter trends on a calibration run.

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
| Background threshold too low/high | Set `fixed_bg_threshold`, or tune `bg_height_pxs` / `bg_color_est_perc` |
| Rough centre unstable | Increase `n_move_aver` |
| Noisy sigma | Increase `blur_est_border_thickness` |

## Performance

The hot paths are vectorized:

- background percentile via cumulative sums over the band;
- row extents via `np.minimum.at` / `np.maximum.at`.

The blur estimate only touches the cropped square around the detected sphere;
the full image is used for the mask and the background estimate.
