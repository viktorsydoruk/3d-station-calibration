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
- Optional Ice-session archiving: each session writes 8-bit TIFF frames,
  `Calibration3DPositions.csv`, the latest `calibration_result.yaml`, and
  `session.yaml` directly into its date folder's `data` directory.
- Procedure-based Ice sessions: `init(int procedureId, optional string
  configurationfilepath)` resolves `<procedures-root>/<procedure-id>/config.toml`,
  creates `<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/` with a merged
  `config.toml` and `data/`, and returns the date folder. The optional absolute
  override is recursively merged over the procedure default, and switching away
  from an unfinished procedure is rejected. If a procedure does not exist yet,
  `init` creates it from the packaged default and folds the override into that
  new procedure default; an override for an existing procedure applies only to
  the current run.

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

### Fixed

- Hardened bad-frame handling and CSV input validation.
- Restored the packaged `config.toml` header comment to a valid TOML comment.

<!--
When the first release tag is created, rename [Unreleased] to the release
version, for example:

## [2026.11.2.0] - 2026-11-02
-->
