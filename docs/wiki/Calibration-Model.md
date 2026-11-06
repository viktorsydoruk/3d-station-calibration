# Calibration Model

## Coordinate frames

The fit uses robot coordinates relative to the current sphere home:

```text
X_rel = X_robot - X_home
X_cam = R · X_rel + t
```

`R` is the 3×3 rotation, `t` the translation, and `X_home` the sphere home
position in robot coordinates. Image projection is the standard pinhole model
with OpenCV distortion:

```text
[x, y, w]ᵀ = K · (R · X_rel + t)
u = x / w,   v = y / w
then radial/tangential distortion
```

## Parameter vector

`least_squares` optimizes a flat vector in this order:

```text
fx, fy
[cx, cy]                 only when fix_cx_cy = false
distortion[0:n]          n = n_distortion_coefs
r1, r2, r3               Rodrigues rotation vector
t1, t2, t3               translation in millimetres
```

The distortion names follow OpenCV:

```text
k1, k2, p1, p2, k3, k4, k5, k6, s1, s2, s3, s4, τx, τy
```

Only the first `n` entries are active; the rest are stored as zeros. `params_names`
returns the exact names for the current configuration.

## Initialization

1. **Initial rotation.** `estimate_r_initial` builds pseudo-3D camera points

   ```text
   (u, v, -(radius - 2·sigma))
   ```

   and takes the correlation matrix between those points and the robot
   positions. The 3×3 block is projected onto the nearest proper rotation with
   an SVD polar decomposition (reflections removed). Degenerate or non-finite
   inputs fall back to the identity.
2. **Initial parameters.** `fx = fy = focal_length_initial`, `cx/cy` at the
   image centre when free, distortion zeros, `rvec` from the rotation, and
   `t = (0, 0, camera_distance_initial)`.

> **Sigma offset.** The stored and cached blur sigmas remain the raw
> edge-profile estimates. Every numerical consumer (`calibrate_camera`,
> `find_robot_home_pos_shift`, and `get_nozzle_end_home_position`) adds
> `SIGMA_OFFSET = 0.5 px` before using them. The offset keeps a zero sigma
> usable as a weight and accounts for sub-pixel uncertainty not captured by the
> edge fit. Freshly analyzed and cached observations therefore behave the same.

## Residuals and loss

`residuals` projects all robot points with `cv2.projectPoints` and returns

```text
predicted - measured
```

flattened to `2N` values. `calibrate_camera` calls `scipy.optimize.least_squares`
with:

```python
loss="soft_l1"
f_scale=5.0
x_scale="jac"
```

`soft_l1` limits the influence of gross outliers; `f_scale` is the pixel scale
at which residuals start being downweighted. The default is `5.0 px`, matching
ordinary reprojection errors in the calibration fixture; SciPy's implicit
default of `1.0 px` would treat normal residuals as outliers. The scale is
configurable as `[analysis.fit] loss_f_scale` in pixels. `x_scale="jac"` gives
parameter-aware scaling. There are no bounds and no analytical Jacobian.

The fit also validates that `robot_positions` is `(N, 3)`, `image_center_points`
is `(N, 2)`, the lengths match, and `N >= 10 + n_distortion_coefs`.

> The residuals are unweighted. `radii` and `sigmas` are used for the initial
> rotation and by the home-shift stage, not as per-point weights in the camera
> fit.

## Distortion fallback

After each fit `check_distortion_monotonicity` evaluates OpenCV's rational
radial scale

```text
scale = (1 + k1·r² + k2·r⁴ + k3·r⁶) /
        (1 + k4·r² + k5·r⁴ + k6·r⁶)
```

and the distorted radius `r · scale`. It samples `r` from 0 to the largest
normalized radius over the four image corners, computed with the fitted `fx`,
`fy`, `cx`, and `cy`. The model is accepted only if both the scale and distorted
radius stay positive and `r · scale` increases monotonically over that domain.
Checking the scale alone is insufficient because a positive but decreasing scale
can still fold the radial mapping.

If the check fails, `get_calibration_data` refits with
`n_distortion_coefs = 0`. The `CalibrationResult.n_distortion_coefs` and the YAML
output then reflect the fallback value, even if the configured value was larger.

## Iterative pipeline

`get_calibration_data` is the whole numerical pipeline:

1. Set `X_home = mean(robot positions)` and `X_rel = X - X_home`.
2. Determine the number of outlier-removal iterations from
   `max_outliers` / `allowed_outliers`.
3. For each outlier iteration:
   1. Repeat `n_iterations` times:
      - fit the camera on the current mask;
      - estimate the home shift and update `X_home` / `X_rel`;
      - adjust the apparent image centres with `adjust_image_center_points`;
      - carry the fitted `fx` and `t_z` into the next fit as initial values.
   2. Refit once after the last centre adjustment, so the returned matrices
      correspond to the returned centres.
   3. Compute residual vectors `(dx, dy)` per point.
   4. Record the candidate if its RMSE is better than the previous best.
   5. Flag points with `|dx| > 2·std(dx)` or `|dy| > 2·std(dy)`.
   6. If any are flagged and another removal is allowed, remove the point with
      the largest squared flagged residual (provided more than `min_points`
      remain).
   7. Repeat with the reduced mask.
4. Return the best candidate: home, adjusted centres, `K`, `E`, distortion,
   `OptimizeResult`, RMSE, outlier mask, and the effective distortion count. The
   returned mask and result therefore always describe the same point set.

### `max_outliers` semantics

| Value | Maximum removals |
| --- | --- |
| `0` | One fit pass; no removal |
| `0 < x < 1` | `int(N·x)` |
| `x >= 1` | `int(x)` |

The count is capped at `N - min_points`. Removal also requires strictly more than
`min_points` active points. The pipeline always performs one initial fit pass,
then evaluates at most that many additional removal candidates.

### Apparent-centre correction

`adjust_image_center_points` uses the angle-bisector relation. The observed
silhouette centre of a projected sphere is not exactly the projection of its 3D
centre; the correction shifts the measured centre using the apparent radius and
the focal lengths, with the principal point as reference. This is why the
pipeline adjusts centres after every fit and refits.

## Outlier mask and result

`get_calibration_data` returns a boolean mask over the points passed to it.
`CalibrationSession` maps that mask back onto all stored observations:

- `fit_observation_indices` — indices that survived radius filtering;
- `fit_mask` — mask over those indices after calibration outliers;
- `used_mask` — the same selection over all session observations;
- `n_used` — `used_mask.sum()`.

## Uncertainties

`calculate_errors` (in `support.py`):

1. Requires more residuals than parameters.
2. Computes `sigma² = SSE / (m - n)`.
3. Uses the Moore–Penrose pseudoinverse of the Jacobian:
   `cov = sigma² · pinv(J) · pinv(J)ᵀ`.
4. Returns `sqrt(diag(cov))`. Rank-deficient problems use the pseudoinverse and
   stay finite; `NaN` is returned when the degrees of freedom are non-positive
   or the residuals/Jacobian are not finite.

`calculate_calibration_errors` maps that flat vector onto the public shapes:

| Output | Shape | Notes |
| --- | --- | --- |
| `intrinsic_std` | 3×3 | `[0,0] = σfx`, `[1,1] = σfy`; `[0,2]/[1,2]` only when `cx/cy` are free; structurally fixed entries, including `[2,2]`, are 0 |
| `distortion_std` | 14 | First `n_distortion_coefs` entries populated |
| `rot_vec_std` | 3 | Rotation-vector components |
| `tra_vec_std` | 3 | Translation components |

The covariance formula assumes independent, identically distributed residuals
and an ordinary least-squares objective. With `soft_l1` the reported values are
indicative rather than exact.

## Metrics and reporting

- `calculate_RMSE(result, standardized=False)` — `sqrt(SSE / m)`.
- `calculate_RMSE(result, standardized=True)` — `sqrt(SSE / (m - n))`, `NaN` if
  no degrees of freedom remain.
- `print_calibration` — matrices, distortion, optimizer status, and each
  parameter with its one-sigma value.
- `back_projected_point` — project a 3D point into the image with the fitted
  model.

## Known limitations

- **Principal point.** With `fix_cx_cy = true` it is exactly the image centre.
  Estimating it requires a well-distributed dataset; otherwise `cx`/`cy` are
  weakly constrained and correlated with the rotation and translation.
- **High-order distortion.** Coefficients such as `k2` or `k5` can have large
  formal uncertainties. The monotonicity check is a guard against physically
  implausible solutions, not a substitute for enough data.
- **Robust loss.** `soft_l1` handles occasional bad detections, but the
  reported covariance is an approximation.
- **Relative frame.** `E` maps positions relative to `pos_home`; the absolute
  home is returned separately and is used for the nozzle position.
