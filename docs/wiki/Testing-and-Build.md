# Testing and Build

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite currently collects **139 tests** and runs without network access.
`pytest` is configured in `pyproject.toml` with `testpaths = ["tests"]` and
`pythonpath = ["src"]`.

| Test module | Coverage |
| --- | --- |
| `test_settings.py` | Defaults, overrides, path resolution, validation |
| `test_stop.py` | Stop policy ordering and details |
| `test_session.py` | Add/fit/finish, radius filter, readiness, masks |
| `test_service.py` | Bytes/array service path and rejections |
| `test_folder.py` | Folder source, cache loading, rejections |
| `test_processes.py` | Iterative pipeline and fit behaviour |
| `test_image.py` | Background, sphere detection, blur sigma |
| `test_metrics.py` | Uncertainty mapping and RMSE |
| `test_storage.py` | Point cache and YAML round-trips |
| `test_debug.py` | Debug image writing |
| `test_ice_adapter.py` | Servant mapping, caches, loopback when Ice is installed |

`test_ice_adapter.py` is skipped when the optional `zeroc-ice` dependency is not
installed.

## Lock file

```powershell
uv lock --check
```

Verifies that `uv.lock` matches `pyproject.toml`. The repository currently locks
52 packages.

> After changing `version` or dependencies, run `uv lock` once. `uv lock --check`
> fails until the lock metadata matches `pyproject.toml`.

## Build

```powershell
uv build
```

Hatchling produces:

```text
dist/3dstationcalibration-2026.10.25-py3-none-any.whl
dist/3dstationcalibration-2026.10.25.tar.gz
```

### Wheel contents

- the `station_calibration` package, including `resources/config.toml`;
- the Ice adapter, server, client, and generated stubs;
- `LICENSE` and `THIRD_PARTY_NOTICES.md` as license files.

ZeroC Ice is **not** bundled; it remains an optional extra.

### sdist contents

```text
src/station_calibration
tests
ice
_3dsc_resources/CalibrationPhenoseederIcing.ice
README.md
LICENSE
THIRD_PARTY_NOTICES.md
pyproject.toml
```

## Versioning

The version is date-based (`2026.10.25`). Update it in `pyproject.toml` when
producing a release, then re-run:

```powershell
uv lock --check
uv build
```

## Optional extras

```powershell
uv sync --extra ice
uv sync --extra notebooks
```

The `dev` dependency group (`pytest`, `scipy-stubs`) is installed by `uv sync`.
