# Python API

The public API is re-exported from `station_calibration`; callers should not
depend on the internal module layout.

## Main exports

| Group | Names |
| --- | --- |
| Settings and lifecycle | `Settings`, `PossibleOptions`, `DebugInfo`, `StopPolicy`, `StopReason`, `StopStatus`, `DEFAULT_TARGET_OBSERVATIONS`, `ReadinessPolicy`, `ReadinessStatus`, `ReadinessTolerances`, `FitSnapshot` |
| Domain and session | `CalibrationObservation`, `ObservationRejection`, `CalibrationResult`, `SIGMA_OFFSET`, `CalibrationSession`, `CalibrationService` |
| Sources | `ObservationDataset`, `ObservationSource`, `FolderDataset`, `FolderCalibrationSource`, `create_folder_session`, `observations_to_arrays` |
| Image analysis | `SphereObservation`, `ImageAnalysisResult`, `load_image`, `decode_image`, `split_image`, `analyze_image`, `analyze_image_array`, `analyze_image_bytes`, `analyze_images`, `get_sphere_centers_and_blur_sigmas`, `get_radius_outlier_mask`, `filtering_data_by_radius`, `adjust_image_center_points` |
| Numerical pipeline | `get_calibration_data`, `get_3D_and_2D_data`, `print_calibration`, `get_calibration`, `calibrate_camera`, `check_distortion_monotonicity`, `radial_distortion_scale`, `radial_scale_profile`, `back_projected_point`, `calculate_RMSE`, `calculate_calibration_errors` |
| Robot/geometry | `find_robot_home_pos_shift`, `get_nozzle_end_home_position`, `find_proper_args_to_compare`, `fit_line_general_form`, `intersect_lines`, `calculate_errors` |
| Uncertainty | `bootstrap_nozzle_home`, `NozzleBootstrapResult` |
| I/O | `load_robot_positions`, `search_images`, `store_all_points`, `load_all_points`, `RESULT_SCHEMA_VERSION`, `calibration_document`, `store_calibration`, `NOZZLE_UNCERTAINTY_SCHEMA_VERSION`, `store_nozzle_uncertainty` |
| Plotting | `visualize_*`, `apply_own_style_to_mpl` (lazy imports) |

Plotting helpers are loaded on first access, so importing the package does not
import `matplotlib.pyplot`.

## Folder session

```python
from pathlib import Path

from station_calibration import Settings, create_folder_session

folder = Path(r"P:\3Dcalibration\3D_example")
settings = Settings(folder)

session = create_folder_session(settings)   # fit_every_n=None by default
result = session.finish()

print(result.intrinsic_matrix)
print(result.extrinsic_matrix)
print("RMSE:", result.rmse, "used:", result.n_used)
print("home:", result.pos_home)
```

`create_folder_session` loads a cache or analyzes the images, adds rejections and
observations, and returns a session. With `fit_every_n=None`, exactly one fit is
performed by `finish()`.

To mirror the configured CLI cadence, pass `settings.fit_every_n`:

```python
session = create_folder_session(settings, fit_every_n=settings.fit_every_n)
```

`settings.fit_every_n` is `None` when `[analysis] fit_every_n = 0`.

## Incremental service

```python
import cv2
import numpy as np

from station_calibration import CalibrationService, Settings

settings = Settings(r"P:\3Dcalibration\3D_example", load_stored_data=False)
service = CalibrationService(settings, fit_every_n=10)

frame = cv2.imread("frame_0001.tif", cv2.IMREAD_UNCHANGED)
robot_position = np.array([12.5, -40.0, 81.2], dtype=np.float64)

service.add_image_array(frame, robot_position)

if service.is_ready:
    result = service.finish()
    print(result.intrinsic_matrix)
```

Encoded bytes work the same way:

```python
service.add_image_bytes(Path("frame_0001.tif").read_bytes(), robot_position)
```

The service applies the same settings-to-analysis mapping as folder mode,
records rejections, and refits according to `fit_every_n`.

## Analyze, then add

```python
from station_calibration import CalibrationSession, Settings, analyze_image_array

settings = Settings(folder)
session = CalibrationSession(settings)

analysis = analyze_image_array(frame, image_index=0)
if analysis.observation is None:
    print("rejected:", analysis.reason)
else:
    session.add_analysis(analysis, robot_position, source="camera")

result = session.finish()
```

`analyze_image_array` accepts the same keyword arguments as `analyze_image`
(background, sphere projection, debug options).

## Uncertainties

```python
from station_calibration import calculate_calibration_errors

intrinsic_std, distortion_std, rot_std, trans_std = calculate_calibration_errors(
    result.optimize_result,
    fix_cx_cy=settings.fix_cx_cy,
    n_distortion_coefs=result.n_distortion_coefs,
)
```

`intrinsic_std` is a 3×3 matrix; structurally fixed entries, including
`[2, 2]`, are zero.

The nozzle home is not part of the camera-fit parameter vector. Estimate its
uncertainty from the inlier observations with the residual bootstrap:

```python
from station_calibration import bootstrap_nozzle_home

uncertainty = bootstrap_nozzle_home(
    session.fit_observations,
    result,
    settings,
    n_bootstrap=500,
    seed=0,
)

print(uncertainty.original)
print(uncertainty.std)
print(uncertainty.covariance)
```

The bootstrap keeps the original inlier set and the commanded robot positions
fixed, perturbs image centres with their stored covariance, resamples
radius/sigma residuals, and reruns the fit for each replicate.

## Settings and overrides

```python
settings = Settings(
    folder,
    config_file="custom.toml",
    debug=False,
    n_distortion_coefs=5,
    fix_cx_cy=True,
    target_observations=400,
)
```

`None` values mean “use the TOML value”. Unknown keywords raise
`ValueError`.

## Error handling

| Exception | Typical cause |
| --- | --- |
| `FileNotFoundError` | Config, robot CSV, or cache missing |
| `ValueError` | Invalid shapes, too few observations, bad settings |
| `KeyError` | Missing TOML section/key |
| `RuntimeError` | Ice getter before any successful fit |

A failed fit is re-raised and also stored in `session.last_fit_error`.

## Low-level helpers

```python
from station_calibration import calibrate_camera, get_calibration

fit = calibrate_camera(
    robot_positions,
    image_center_points,
    radii,
    sigmas,
    image_size_xy=(2500, 2000),
    fix_cx_cy=True,
    n_distortion_coefs=4,
)
K, distortion, rvec, E = get_calibration(
    fit.x,
    image_size_xy=(2500, 2000),
    fix_cx_cy=True,
    n_distortion_coefs=4,
)
```

`robot_positions` must already be relative to the home frame used by `E`.
