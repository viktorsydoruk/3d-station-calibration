# Home and Nozzle

The camera fit produces a model in a frame relative to the sphere home. Two
separate geometric steps recover the physical robot quantities:

1. `find_robot_home_pos_shift` — where the sphere home lies in robot coordinates
   and at which depth it is sharpest.
2. `get_nozzle_end_home_position` — where the nozzle tip is, using the sphere
   diameter and the nozzle direction.

The home shift is iterated with the camera fit inside `get_calibration_data`;
the nozzle position is computed from the final fit. Both estimators use the
stored blur sigmas plus `SIGMA_OFFSET = 0.5 px`; see
[Calibration Model](Calibration-Model#initialization).

## Sphere home shift

Inputs are robot positions already relative to the current home, the adjusted
image centres, `K`, `E`, distortion, and the blur sigmas.

### 1. Rotate into camera orientation

```python
coords = R @ X_rel
```

Only the rotation is applied. The translation is a constant offset and does not
affect the *shift* being estimated.

### 2. Undistort the image centres

```python
image_center_points_undist = cv2.undistortImagePoints(points, K, distortion)
```

### 3. Depth shift from defocus

The sphere is sharpest in the focal plane, so the edge blur is smallest there:

```python
popt = polyfit(z_cam, sigma, deg=4, w=1 / (r_xy² + sigma²))
z_shift = x[argmin(polyval(popt, x))]     # x is a 101-point grid over z_cam
```

The weighting combines the radial distance from the optical axis and the blur
itself.

### 4. Lateral shift from the principal point

The image position is approximately linear in the camera-frame coordinate:

```python
popt_x = polyfit(x_img, x_cam, deg=1, w=1 / sigma²)
x_shift = polyval(popt_x, cx)

popt_y = polyfit(y_img, y_cam, deg=1, w=1 / sigma²)
y_shift = polyval(popt_y, cy)
```

Evaluating at `cx`/`cy` gives the camera-frame offset whose projection lands on
the principal point.

### 5. Back to robot coordinates

```python
shift_robot = Rᵀ @ [x_shift, y_shift, z_shift]
```

The caller then performs:

```python
pos_home += shift_robot
X_rel    -= shift_robot
```

and repeats after the next camera fit. Because the principal point, distortion,
and home are updated together, the final quantities are mutually consistent.

> **Sensitivity**
> The lateral home position depends on the principal point through `cx`/`cy`.
> In the reference setup (`fx ≈ 1.48e4`, depth ≈ 80 mm), a 10 px principal-point
> error corresponds to about 0.05 mm at the home. With the default
> `fix_cx_cy = true`, the principal point is fixed at the image centre.

## Nozzle-end home

`get_nozzle_end_home_position` returns `(nozzle_position, sphere_diameter, debug)`.

### 1. Scale millimetres per pixel

```python
robot_camera_coords = R @ X_rel
px = ||undistorted_center - (cx, cy)||
mm = ||robot_camera_coords[:2]||
```

Only points farther than half the maximum radial distance are used, which keeps
the fit in the well-conditioned part of the field:

```python
mask = mm > max(mm) / 2
popt = polyfit(z_cam[mask], (mm / px)[mask], deg=2)
coef = polyval(popt, z_cam)
```

`coef` is the local mm-per-pixel scale for every observation.

### 2. Sphere radius with sub-pixel edge correction

The detected radius is biased by the edge blur. Scan `n_sigma` from 0 to 4:

```python
std_radii = [std(2 * (radius - n_sigma * sigma) * coef) for n_sigma in grid]
n_sigma_est = grid[argmin(std_radii)]
sphere_radius = mean((radius - n_sigma_est * sigma) * coef)
```

The factor `2` converts radius to diameter; the scan picks the blur correction
that makes the physical diameter most consistent across depths.

### 3. Offset from sphere centre to nozzle tip

The nozzle is modelled as an offset from the sphere centre along the camera
`±y` axis:

```python
direction = unique(directions)  # exactly one of +1 or -1
offset_cam = [0, direction * sphere_radius, 0]
nozzle_cam = R @ sphere_home + offset_cam
nozzle_robot = Rᵀ @ nozzle_cam
```

Mixed or undefined directions are rejected instead of being averaged into a
zero offset.

Because `R` and `Rᵀ` cancel, this is equivalent to

```text
nozzle_robot = sphere_home + Rᵀ · [0, sign·r, 0]
```

so only the orientation of the offset matters, not the extrinsic translation.
The returned diameter is `2 * sphere_radius`.

## Nozzle-home uncertainty

`calculate_calibration_errors` reports only the camera parameters. The nozzle
home is a post-fit function of the sphere home, the sphere radius, and the
rotation:

```text
nozzle_robot = sphere_home + sign * radius * Rᵀ · e_y
```

The sphere home and radius are not part of `OptimizeResult.jac`, so their
uncertainty is not included in the reported `fx/fy/distortion/rotation/
translation` errors. Use the residual-bootstrap diagnostic instead:

```powershell
python scripts/bootstrap_nozzle.py <folder> --load-stored-data --n-bootstrap 500
```

The folder analysis can also produce the report after its normal fit:

```powershell
3dsc <folder> --bootstrap
```

This writes `output/nozzle_uncertainty.json`; the main
`calibration_data.yaml` is unchanged. Use `--bootstrap-n` and
`--bootstrap-seed` to override the config values, or set
`[analysis.uncertainty] enabled = true` in the TOML file.

The standalone script additionally supports `--ready` to bootstrap the first
readiness snapshot instead of all observations, and `--json <file>` to choose
the output path.

The diagnostic:

1. fixes the original inlier set;
2. perturbs image centres with their stored 2 x 2 covariance;
3. resamples radius/sigma residuals around the fitted depth trends;
4. keeps the commanded robot positions fixed;
5. reruns the camera fit and `get_nozzle_end_home_position`;
6. reports the mean, bias, covariance, per-axis 1 sigma, 1 sigma/2 sigma
   intervals, and the uncertainty along and perpendicular to the nozzle axis.

The result is conditional on the inlier selection, the camera model, and the
radius/sigma trends. It does not model robot-positioning errors or a wrong
sphere diameter, and it is a diagnostic rather than an input to the readiness
gate.

## Assumptions

- The sphere is centred on the nozzle axis.
- The nozzle offset is along the camera's `±y` axis, selected by the common image
  direction (`+1` top, `-1` bottom).
- All images use a consistent nozzle orientation; mixed directions raise an
  error.
- The quadratic mm/px fit is valid over the working depth range.
- Enough points exist at varied depths for both the quartic sigma fit and the
  quadratic scale fit.

## Debug data

`get_nozzle_end_home_position` returns a dictionary with:

| Key | Content |
| --- | --- |
| `scaling_visualization` | `z_pos`, `mm/px`, quadratic fit coefficients |
| `n_sigma_estimation` | sigma grid and diameter standard deviation |
| `sphere_radius_estimation` | depths, radii, sigmas, scale coefficients, chosen sigma |
| `sphere_radius_vs_depth` | the same data with the zero-depth scale |

These are plotted by `visualize_results` when debug output is enabled.
