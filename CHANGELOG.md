# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions use
calendar versioning in the form `YYYY.MM.DD.N`.

## [Unreleased]

### Added

- First tagged calendar-version release, generated from Git tags by `hatch-vcs`.
- `--version` for `3dsc`, `3dsc-ice-server`, and `3dsc-ice-client`, plus
  `station_calibration.__version__`.
- Windows Task Scheduler and Raspberry Pi systemd timer automatic updaters with
  release-tag filtering, health checks, and rollback.
- Optional updater signature verification and annotated-tag enforcement.
- `scripts/release.py` helper for clean, reproducible release tags.
- GitLab CI checks for tests, wheel/sdist builds, and shell syntax.
- Deployment, manual update, rollback, and troubleshooting documentation for
  Windows and Raspberry Pi.
- Optional Ice-session archiving: each session writes compressed TIFF frames at
  the source dtype and bit depth, `Calibration3DPositions.csv`, the latest
  `calibration_result.yaml`, and `session.yaml` directly into its date folder's
  `data` directory. TIFF frames use Adobe Deflate compression; wider frames are
  no longer rescaled to 8 bit per frame, and boolean frames are stored as
  `uint8`.
- Procedure-based Ice sessions: `init(int procedureId, optional string
  configurationfilepath)` resolves `<procedures-root>/<procedure-id>/config.toml`,
  creates `<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/` with a merged
  `config.toml` and `data/`, and returns the date folder. The optional absolute
  override is recursively merged over the procedure default, and switching away
  from an unfinished procedure is rejected. If a procedure does not exist yet,
  `init` creates it from the packaged default and folds the override into that
  new procedure default; an override for an existing procedure applies only to
  the current run.
- Ice `finish()` and `abort()` operations. `finish` forces a final fit even when
  the configured `target_observations` stop condition has not been reached and
  returns whether a result is available; `abort` discards the live session and
  allows another procedure to be selected. Archived session data remains on
  disk after `abort`.
- `[analysis] fit_every_n` controls how often a running session refits; `0`
  disables intermediate fits and waits for `finish()`.
- A versioned, shared result document for the folder CLI and Ice archive, with
  consistent `schema_version`, `nozzle`, and `camera` sections.
- GitLab CI now installs ZeroC Ice from the official Debian repository and runs
  the Ice adapter/client test suite.
- Ruff linting, a formatter configuration, and pre-commit hooks for Python
  checks and common file hygiene.
- Initial `mypy` checking for `src/station_calibration`, with generated Ice
  stubs excluded, third-party imports tolerated, and a CI lint step. Stricter
  per-module checks remain incremental.
- Branch coverage reporting with a `90%` gate, excluding the optional Ice
  transport, published as `coverage.xml` by GitLab CI. Ice tests run in the
  separate `test-ice` job.
- Coverage-driven tests for camera-model packing, fit validation, reporting
  plots, robot geometry, image/storage edge cases, CLI parsing, and the Ice wire
  format.
- A PEP 561 `py.typed` marker so downstream type checkers use the package's
  inline annotations.
- A GitLab CI lint job and updated contributor documentation for the new
  tooling.

### Changed

- The package version is now derived from Git tags instead of a static value in
  `pyproject.toml`.
- All production Slice contracts now live under `ice/`; the stub generator moved
  to `scripts/generate_ice_stubs.py`.
- New releases use annotated `vYYYY.MM.DD.N` tags; legacy `vYYYY.MM.DD` tags are
  treated as revision `0`.
- `3dsc-ice-server` now requires `--config`; the procedures root comes from
  `[general] procedures_root`. The positional server folder and
  `--stations-root` were removed. `3dsc-ice-client` now requires
  `--procedure-id`.
- The packaged `debug` default is now `false`, keeping reporting optional.
- Matplotlib is imported lazily, so the CLI and Ice server start without loading
  the plotting stack.
- Calibration result and session metadata YAML files are written via a temporary
  file and atomic replacement.
- The Ice server handles `SIGTERM` and `SIGBREAK` like `Ctrl+C`, closing the
  active archive and destroying the communicator cleanly.
- Dead-code cleanup: removed the no-op `visualize_diff_new_old_center_points`
  plotting export and renamed unused callback arguments and fit locals. No
  numerical or runtime behavior changed.
- Contributor documentation now includes a single local quality-gate sequence
  for lock checks, Ruff, mypy, pre-commit, coverage, and release builds.
- Distortion acceptance now checks OpenCV's rational radial model and the actual
  `r * scale` mapping over the true image corners. A valid 4-coefficient model
  in the stored regression fixture is kept instead of falling back to zero
  distortion, so that fixture's expected values were updated.
- Outlier removal treats `max_outliers` as a maximum number of removals, runs
  one initial fit plus at most that many removal candidates, and returns the
  best-RMSE candidate with a mask that matches its fit.
- `intrinsic_std[2,2]` is now `0.0` because it is not a fitted parameter.
- `bg_height_pxs` now requires at least 10 rows, and numeric settings reject
  `NaN`/infinity during configuration loading.

### Fixed

- Hardened bad-frame handling and CSV input validation.
- Restored the packaged `config.toml` header comment to a valid TOML comment.
- A procedure that cannot reach its `target_observations` no longer locks out
  other procedures; call `finish()` to keep the result or `abort()` to discard
  the live session.
- Failed or non-converged fits are no longer published or archived; the previous
  successful result is retained and `last_fit_error` explains the failure.
- Nozzle and sphere-diameter estimation now use only the observations that
  survived the calibration outlier filter.
- Blur sigmas accept zero and receive a `0.5 px` offset inside the numerical
  estimators, preventing division-by-zero weights without changing cached data.
- Re-initializing an Ice procedure while its session has unfinalized data now
  raises a clear error asking the client to call `finish()` or `abort()` first.
- Folder batch analysis records missing, unreadable, or corrupt frames as
  rejections and continues with the remaining images.
- The point cache is written through an atomic temporary file, so a crash no
  longer leaves a truncated `CalibrationAllPoints.dat`.
- Debug rendering copies the source frame before drawing, so read-only Ice
  frames are no longer mutated.
- The Ice client sets `Ice.MessageSizeMax` to match the server by default,
  avoiding connection loss on full-resolution raw frames.
- A session that received only rejected frames no longer blocks a later
  procedure switch.
- Mixed nozzle directions and non-positive sphere radii are rejected instead of
  silently producing an averaged offset.
- Client-supplied Ice configuration overrides can no longer set absolute or
  parent-traversing session file paths; server-owned procedure defaults may
  still use absolute paths.
- The first automatic fit now runs as soon as the minimum observations survive
  radius filtering, even when `fit_every_n` is larger; later refits still use
  the configured cadence.

<!--
When the first release tag is created, rename [Unreleased] to the release
version, for example:

## [2026.11.2.0] - 2026-11-02
-->
