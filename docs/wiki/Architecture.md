# Architecture

The package has one source-agnostic calibration engine and two frontends:
folder and ZeroC Ice. Both analyze one image at a time, create the same domain
objects, and feed the same `CalibrationSession`.

## Package layout

```text
src/station_calibration/
├─ __init__.py              explicit public API, lazy plotting exports
├─ __main__.py              python -m station_calibration
├─ cli.py                   folder workflow and 3dsc entry point
├─ debug.py                 DebugInfo printing helper
├─ settings.py              TOML-backed settings and overrides
├─ stop.py                  StopPolicy / StopReason / StopStatus
├─ models.py                observation, rejection, and result dataclasses
├─ session.py               incremental calibration session
├─ service.py               image bytes/arrays -> analysis -> session
├─ processes.py             iterative fit + home-shift pipeline
├─ robot.py                 home-shift and nozzle-home geometry
├─ support.py               line geometry and uncertainty helpers
├─ plots.py                 optional debug/reporting plots
├─ resources/
│  └─ config.toml           packaged default configuration
├─ vision/
│  ├─ io.py                 load/decode/split images
│  ├─ detection.py          background, mask, sphere, blur sigma
│  ├─ analysis.py           single-image and batch analysis
│  ├─ geometry.py           apparent-centre adjustment
│  ├─ debug.py              debug-image rendering
│  └─ models.py             SphereObservation / ImageAnalysisResult
├─ calibration/
│  ├─ initialization.py     initial rotation and parameter packing
│  ├─ model.py              projection, residuals, parameter unwrapping
│  ├─ fit.py                scipy least-squares fit
│  └─ metrics.py            monotonicity, uncertainties, reporting
├─ storage/
│  ├─ inputs.py             robot CSV and image discovery
│  ├─ points.py             point-cache serialization
│  └─ results.py            calibration YAML
├─ sources/
│  ├─ base.py               ObservationSource / ObservationDataset protocols
│  └─ folder.py             folder source adapter
└─ ice/                     optional ZeroC Ice frontend
   ├─ adapter.py            CalibrationIceServant
   ├─ server.py             server CLI
   ├─ client.py             synchronous client and CLI
   ├─ _generated.py         adds generated stubs to sys.path
   └─ generated/            committed slice2py output
```

## Layering

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Domain | `models.py`, `stop.py` | Value objects and readiness rules |
| Vision | `vision/*` | Image → sphere centre/radius/sigma/direction |
| Calibration | `calibration/*` | Camera model, fit, uncertainties |
| Pipeline | `processes.py`, `robot.py` | Iterative fit, home shift, nozzle home |
| Session | `session.py`, `service.py` | Fit policy, observation storage, readiness |
| I/O | `storage/*` | CSV, point cache, YAML |
| Frontends | `cli.py`, `sources/folder.py`, `ice/*` | Folder and Ice entry points |

The important dependency rule is that `CalibrationSession` imports neither the
folder layout nor Ice. It only sees `Settings`, `CalibrationObservation`,
`ObservationRejection`, and the numerical pipeline.

## Data flow

```text
image file ──► load_image / split_image ──► analyze_image ──► ImageAnalysisResult
                                                                   │
robot CSV ──► CalibrationObservation ──────────────────────────────┤
                                                                   ▼
                                                        CalibrationSession
                                                                   │ fit()
                                                                   ▼
                                                        get_calibration_data()
                                                                   │
              ┌────────────────────────────────────────────────────┼──────────────────────┐
              ▼                                                    ▼                      ▼
       camera least-squares fit                          home-shift iteration      distortion fallback
              │                                                    │
              └──────────────────────────► CalibrationResult ◄─────┘
                                                   │
                          ┌────────────────────────┼─────────────────────────┐
                          ▼                        ▼                         ▼
                 get_nozzle_end_home_position  calculate_calibration_errors  store_calibration
```

## Frontends

### Folder

`cli.main()` uses `FolderCalibrationSource` to load either a point cache or all
images. It feeds every observation into `CalibrationSession` with
`fit_every_n = 1`, then calls `finish()` once. The final result is converted into
the YAML file and optional plots.

### Ice

`CalibrationIceServant` owns a `CalibrationService`. `addData` analyzes one
image, adds the observation to the service's session, and the service refits
according to the same fit policy. `isReady` and the getters query the session.
See [Ice Interface](Ice-Interface).

### Direct library use

Callers can skip the frontends:

```python
from station_calibration import CalibrationSession, analyze_image_array, Settings

settings = Settings(folder)
session = CalibrationSession(settings)
analysis = analyze_image_array(frame)
session.add_analysis(analysis, robot_position)
result = session.finish()
```

## Design rules

- **One image at a time.** `addData`/`add_image_*` accept a single frame.
- **Rejections are separate.** They are recorded but never counted as valid
  observations.
- **Fit policy is centralized.** `min_observations`, `fit_every_n`, and the
  radius filter live in the session, not in the frontends.
- **Readiness is separate from fitting.** `is_ready` only evaluates the stop
  policy; call `finish()` before reading results.
- **Optional Ice.** The core package imports no Ice modules; the extra is only
  loaded by `station_calibration.ice`.
- **Lazy plotting.** `station_calibration.__getattr__` imports `plots.py` on
  first use so headless callers do not load `matplotlib.pyplot`.
