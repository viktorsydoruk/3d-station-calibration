# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions use
calendar versioning in the form `YYYY.MM.DD.N`.

## [Unreleased]

### Added

- Opt-in noise-aware automatic background threshold. With
  `fixed_bg_threshold = 0`, `bg_threshold_method = "mad"` uses the larger of
  `median + bg_noise_sigma * 1.4826 * MAD` and the `bg_color_est_perc`
  percentile over the quietest background rows. `bg_noise_sigma` defaults to
  `5.0`; its confidence level does not drift with the number of background
  pixels. The percentile floor prevents a zero-MAD collapse on quantized 8-bit
  backgrounds. The packaged default remains `"percentile"`;
  `fixed_bg_threshold != 0` is unchanged.
- Direct tests for the MAD threshold, both automatic methods on a noisy
  synthetic scene, and `bg_threshold_method` / `bg_noise_sigma` validation.
- Direct `estimate_direction` tests for top/bottom scenes, flat frames, short
  frames, and invalid arguments, plus background-estimation regression tests
  for a bright object inside the background band.
- A `BG_stats` debug line with the selected band median, MAD, percentile,
  threshold, prefix length, and foreground fraction. It makes threshold
  failures distinguishable from missing-sphere failures.
- `scripts/background_regression.py`, a manual real-data check that compares
  the percentile, floored MAD, and fixed-threshold methods on the accepted
  dark-background calibration folders.

### Fixed

- `estimate_direction` keeps the top and bottom bands disjoint on frames
  shorter than twice the requested band height. Previously both sides could
  sample the whole image and report an undefined direction.
- `get_bg_value` rejects percentiles outside `(0, 100]`, and
  `get_forground_mask` validates the image shape and threshold instead of
  failing inside OpenCV.
- `analyze_image` reports a threshold that is below the darkest pixel or at or
  above the brightest pixel as `background threshold is outside the usable
  range` instead of a misleading missing-sphere rejection.

### Changed

- The background prefix selection is shared by `get_bg_value` (percentile) and
  the new `get_bg_noise_threshold` (robust MAD), so both methods use exactly
  the same rows.

## [2026.11.10.0] - 2026-11-10

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
- Saturation-based readiness: `[analysis.readiness]` compares two windows of
  fitted camera parameters and reports ready only when they stop changing
  materially. The count floor defaults to `target_observations = 100`; explicit
  and maximum-observation stops remain forced overrides. Count-only readiness is
  restored with `enabled = false` or when automatic fitting is disabled.
- Optional residual-bootstrap nozzle-home uncertainty diagnostic:
  `[analysis.uncertainty]` and `3dsc --bootstrap` rerun the fit with perturbed
  image centres and resampled radius/sigma residuals, then write a sidecar
  `output/nozzle_uncertainty.json`. The standalone
  `scripts/bootstrap_nozzle.py` runner remains available. Robot positions and
  the original inlier set stay fixed, the diagnostic is disabled by default,
  and it does not change the stored calibration or the readiness decision.
- Optional bootstrap confidence interval for the sphere-radius blur correction
  through `get_nozzle_end_home_position(..., n_sigma_bootstrap=...)`; it is off
  by default and does not change the fitted diameter. With the blur-aware
  sub-pixel search the full ceramic interval is `[0, 0.081]` on the grid and
  `[0.004, 0.064]` continuously, below the packaged `0.25 sigma` cap; the cap
  remains a conservative guardrail rather than a statistical estimate.
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
- Optional sub-pixel silhouette refinement for sphere detection:
  `analyze_image(..., subpixel_edges=True)`, the batch wrappers,
  `[analysis.sphere_projection] subpixel_edges` (default `false`), and the
  `--subpixel-edges` CLI flag locate the
  sphere boundary at the 50 % radial intensity crossing instead of the binary
  mask pixel. Each ray estimates its own background and interior level and a
  MAD trim removes inconsistent crossings. On synthetic blurred spheres this
  removes the blur-dependent radius bias (for example, a radius error of
  `+5.7 px` at `sigma = 5 px` becomes about `-0.05 px`) while leaving the
  centre accuracy unchanged. On real sphere sets the empirical blur
  correction fell from up to `1.09 sigma` to `0` and the diameter repeatability
  across independent scans improved, with calibration RMSE changes between
  `-0.20 px` and `+0.06 px`.

### Changed

- The radius-outlier filter now uses the binary-mask radius as a
  method-independent reference when `subpixel_edges = true`. Sub-pixel radii are
  systematically smaller, so the previous absolute `2.5 sigma` filter rejected
  extra high-radius frames; the reference filter keeps the binary set while the
  sub-pixel radius still feeds the fit. On the full ceramic folder this restored
  the binary fit-observation count (489 instead of 481).
- Sub-pixel edge refinement now chooses a blur-aware radial search window on
  the first attempt instead of starting at `0.2 * radius` and retrying only
  after too few rays survive. The window is
  `max(0.2 * radius, 3 * sigma, 1.5 * 0.2 * radius)`, capped at half the binary
  radius; `edge_search_px` remains an explicit override. On the same 479
  matched ceramic observations this reduced the residual `n_sigma_opt` from
  `0.485` to `0.040` and changed the capped diameter from `0.9921 mm` to
  `0.9960 mm`; the full production adaptive fit reports `0.9962 mm` against a
  `0.999 mm` micrometer reference.
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
- Outlier selection now uses a leverage-corrected 2D Mahalanobis score and a
  configurable chi-square threshold (`[analysis] outlier_confidence`, default
  `0.999`) instead of a per-axis `2σ` rule that flagged about 9% of Gaussian
  points. A spatial-cluster guard (`outlier_cluster_guard`, default `true`)
  keeps compact groups of high-score points, which usually indicate a
  systematic robot or camera-model effect rather than isolated blunders.
- Per-observation centre covariance from the circle fit is now propagated
  through image analysis, the point cache, and the calibration fit. With
  `[analysis.fit] center_weighting = true` (default), the camera fit uses
  generalized least squares; raw pixel residuals are retained for RMSE
  reporting, while whitened residuals feed the parameter covariance and outlier
  test. Old caches without covariance columns fall back to the unweighted fit
  until the images are re-analyzed.
- The packaged defaults now use `n_distortion_coefs = 0`, `fit_every_n = 5`,
  and `max_outliers = 10`. The no-distortion model is adequate for the loose
  nozzle-position requirement, and refitting every five observations reduces
  acquisition-time CPU use.
- `intrinsic_std[2,2]` is now `0.0` because it is not a fitted parameter.
- `bg_height_pxs` now requires at least 10 rows, and numeric settings reject
  `NaN`/infinity during configuration loading.
- The `soft_l1` robust loss now uses an explicit `5 px` transition scale
  (`[analysis.fit] loss_f_scale`) instead of SciPy's implicit `1 px` default, so
  ordinary reprojection residuals are not downweighted as gross outliers. The
  stored regression fixture's calibration values were updated accordingly.

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
