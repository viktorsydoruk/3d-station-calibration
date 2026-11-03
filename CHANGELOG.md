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
- Optional Ice-session archiving: each session is written to a `YYYYMMDD_HHMM`
  timestamped folder with 8-bit TIFF frames, `Calibration3DPositions.csv`, the
  latest `calibration_result.yaml`, and `session.yaml`.
- Station profiles for the Ice server: `init("station01")` resolves
  `<stations-root>/station01/config.toml` and
  `<stations-root>/station01/data`, and switching away from an unfinished
  station is rejected.

### Changed

- The package version is now derived from Git tags instead of a static value in
  `pyproject.toml`.
- All production Slice contracts now live under `ice/`; the stub generator moved
  to `scripts/generate_ice_stubs.py`.
- New releases use annotated `vYYYY.MM.DD.N` tags; legacy `vYYYY.MM.DD` tags are
  treated as revision `0`.

### Fixed

- Hardened bad-frame handling and CSV input validation.

<!--
When the first release tag is created, rename [Unreleased] to the release
version, for example:

## [2026.11.2.0] - 2026-11-02
-->
