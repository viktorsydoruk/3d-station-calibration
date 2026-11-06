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
