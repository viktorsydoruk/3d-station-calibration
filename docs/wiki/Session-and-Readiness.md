# Session and Readiness

`CalibrationSession` is the single place that owns observations, fit policy,
radius filtering, and readiness. Folder and Ice frontends both use it.

## Creating a session

```python
from station_calibration import CalibrationSession, Settings

session = CalibrationSession(
    settings,
    min_observations=14,   # optional
    fit_every_n=1,         # default
    apply_radius_filter=True,
    stop_policy=None,      # default from Settings
)
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `settings` | required | Analysis/fit/stop settings |
| `print_debug` | `DebugInfo(settings.debug)` | Progress printer |
| `min_observations` | `10 + n_distortion_coefs` | Minimum valid observations; can only be raised |
| `fit_every_n` | `1` | Auto-fit after this many new observations; `None` disables auto-fit |
| `apply_radius_filter` | `True` | Apply the 2.5σ radius filter before fitting |
| `stop_policy` | from `Settings` | Readiness rule |

The folder CLI and Ice server pass `settings.fit_every_n`; setting
`[analysis] fit_every_n = 0` resolves to `None` and waits for `finish()`.

If `target_observations` or `max_observations` is below `min_observations`,
construction raises `ValueError`.

## Adding data

```python
session.add_observation(observation)          # already analyzed
session.add_analysis(analysis, robot_position) # ImageAnalysisResult + robot point
session.add_rejection(rejection)               # failed analysis
```

`add_analysis` creates a `CalibrationObservation` when the analysis succeeded;
otherwise it stores an `ObservationRejection` and returns `None`. Rejections
never change the valid-observation count or the fit count.

`add_observation` accepts `fit=True/False/None`:

- `True` — fit immediately (still subject to `can_fit`),
- `False` — store only,
- `None` — use the session policy: the first fit happens as soon as enough
  observations survive the radius filter; after that, refit when
  `new_observations_since_fit >= fit_every_n`.

The first automatic fit is not delayed by a large `fit_every_n`. On the
regression fixture with the default minimum of 14 observations, it runs as soon
as 14 observations survive filtering, even if `fit_every_n` is 20 or more.

## Fitting

`fit()`:

1. Requires `n_observations >= min_observations`.
2. Applies the radius filter (unless disabled).
3. Requires at least `min_observations` points after filtering.
4. Requires a known image size.
5. Calls `get_calibration_data` with the filtered arrays.
6. Rejects a fit that did not converge, or that produced non-finite
   parameters, non-positive focal lengths, or an invalid RMSE.
7. Maps the returned outlier mask back onto all stored observations.
8. Stores a `CalibrationResult`.

If anything fails, `last_fit_error` is set to `"TypeName: message"`, the
exception is re-raised, and the previous successful `last_result` is kept. A
successful fit clears the error, increments `fit_count`, and resets
`new_observations_since_fit`.

`finish()` guarantees the result is up to date:

- raises `ValueError` if there are no observations;
- returns the last result when nothing new arrived and no error is pending;
- otherwise performs one more fit.

`finish_if_ready()` returns `None` unless the stop policy says ready.

## Readiness

Readiness is independent of whether the latest fit has run:

```python
session.is_ready       # bool
session.stop_reason    # StopReason
session.stop_detail    # str | None
```

`StopPolicy.evaluate(n_observations, min_observations, explicit_detail=...)`
checks in this order:

1. fewer than `min_observations` → `NOT_READY` (an explicit stop is noted but
   not honoured);
2. explicit stop requested → `EXPLICIT`;
3. `target_observations` reached → `TARGET_OBSERVATIONS`;
4. `max_observations` reached → `MAX_OBSERVATIONS`;
5. otherwise → `NOT_READY`.

`request_stop()` sets the explicit flag; it still requires the minimum number of
observations before `is_ready` becomes true.

Readiness is advisory: reaching the target does not make the session reject
later observations. The caller decides when to stop sending data, then calls
`finish()` (or `finish_if_ready()`) before reading calibration values. If the
caller instead starts a new session, the Ice adapter refuses while the current
one has accepted observations but has not been finished, and tells the client to
call `finish()` or `abort()` first. Ready alone is not enough to discard the live
session. A session that received only rejected frames does not lock the
procedure.

## Radius filtering

- Fresh observations are kept in the session unfiltered; the 2.5σ filter is
  applied at fit time.
- `apply_radius_filter=False` is used when the source already filtered, such as
  a stored point cache.
- Radius outliers stay stored; `used_mask` records which points entered the
  final model.

## Result object

`CalibrationResult` fields:

| Field | Meaning |
| --- | --- |
| `pos_home` | Sphere home position in robot coordinates |
| `center_points_adjusted` | Apparent-centre-corrected image points used by the fit |
| `intrinsic_matrix` | 3×3 `K` |
| `extrinsic_matrix` | 4×4 `[R \| t]` |
| `distortion` | 14 OpenCV coefficients, inactive entries zero |
| `optimize_result` | Raw `scipy.optimize.OptimizeResult` |
| `rmse` | Unstandardized reprojection RMSE |
| `used_mask` | Mask over all session observations |
| `fit_observation_indices` | Indices after radius filtering |
| `fit_mask` | Mask over `fit_observation_indices` after outlier removal |
| `n_distortion_coefs` | Effective count (may be `0` after fallback) |
| `image_size_xy` | `(width, height)` |
| `observation_count` | Valid observations at fit time |
| `n_used` | `used_mask.sum()` |

## Inspection helpers

| Property | Meaning |
| --- | --- |
| `observations` | Tuple of all valid observations |
| `rejections` | Tuple of all rejected analyses |
| `n_observations` / `n_rejections` | Counts |
| `fit_count` | Number of successful fits |
| `last_result` / `last_fit_error` | Last fit or error |
| `is_fitted` | `last_result is not None` |
| `can_fit` | Total count reaches `min_observations` |
| `can_auto_fit` | Count after radius filtering reaches `min_observations` |
| `new_observations_since_fit` | Counter used by `fit_every_n` |
| `image_size_xy` | Largest `(width, height)` seen, including rejections |
| `fit_observations` | Observations passed to the last fit |
| `used_observations` | Observations that survived all filters |

## Service wrapper

`CalibrationService` combines image analysis and a session:

```python
service = CalibrationService(settings, fit_every_n=1)
service.add_image_array(frame, robot_position)
service.add_image_bytes(encoded_bytes, robot_position)
service.add_analysis(analysis, robot_position)
service.add_observation(observation)
```

It also exposes `is_ready`, `stop_reason`, `stop_detail`, `last_result`,
`request_stop`, `finish`, and `finish_if_ready`. The public `service.session`
can be used for inspection.

`add_image_bytes`/`add_image_array` increment an internal image index and use it
for debug names (`ice_0000.png`).

## Concurrency

`CalibrationSession` is not thread-safe. The Ice servant serializes all
operations with an `RLock`; other frontends must provide their own locking if
they call a session from multiple threads.
