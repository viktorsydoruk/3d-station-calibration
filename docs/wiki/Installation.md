# Installation

## Requirements

- **Python 3.13 or newer** (the package declares `requires-python = ">=3.13"`).
- A working OpenCV build (`opencv-python`).
- Windows is the primary production platform; 64-bit Linux (including
  Raspberry Pi OS Trixie) also works. The package itself has no
  platform-specific code.

Runtime dependencies declared in `pyproject.toml`:

```text
matplotlib>=3.11.1
numpy>=2.5.2
opencv-python>=5.0.0.93
pyyaml>=6.0.3
scipy>=1.18.1
```

## Development install with uv

```powershell
uv sync
```

`uv sync` creates `.venv`, installs the package in editable mode, and installs
the `dev` dependency group (`pytest`, `scipy-stubs`).

## Install with pip

Use a Python 3.13+ interpreter that ships pip. A `.venv` created by `uv sync`
contains no pip, so `python -m pip` fails there with `No module named pip`; use
`uv pip install -e .` in that environment, or create a separate one:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Optional extras

| Extra | Purpose | Command |
| --- | --- | --- |
| `ice` | ZeroC Ice server and client | `uv sync --extra ice` or `python -m pip install -e ".[ice]"` |
| `notebooks` | Jupyter kernel for local exploration | `uv sync --extra notebooks` |

ZeroC Ice is deliberately optional. The core package stays Apache-2.0 and does
not vendor Ice; see `THIRD_PARTY_NOTICES.md`.

On Linux, PyPI does not publish a `zeroc-ice` wheel for 3.8.3. Install
`python3-zeroc-ice` from the official ZeroC APT repository and create the venv
with `--system-site-packages`; do not install the `ice` extra there. See
[Deployment and Autostart](Deployment.md) for the exact Raspberry Pi commands.

## Entry points

Three console scripts are installed:

| Script | Module | Purpose |
| --- | --- | --- |
| `3dsc` | `station_calibration.cli:run_cli` | Folder calibration workflow |
| `3dsc-ice-server` | `station_calibration.ice.server:run_cli` | Ice server |
| `3dsc-ice-client` | `station_calibration.ice.client:run_cli` | One-image Ice client |

The folder workflow is also reachable as a module:

```powershell
python -m station_calibration path\to\calibration-folder
```

## Verify the installation

```powershell
uv run pytest -q
```

`uv sync` installs pytest with the `dev` group; with a pip-only environment,
install it first (`python -m pip install pytest`) and run
`python -m pytest -q`. If ZeroC Ice is not installed,
`tests/test_ice_adapter.py` is skipped entirely.

## Updating

```powershell
uv sync
uv lock --check
uv build
```

`uv lock --check` verifies that `uv.lock` matches `pyproject.toml`; `uv build`
produces the wheel and the source distribution in `dist/`.

The package version is generated from Git tags by `hatch-vcs`, so no version
string needs to be edited. Verify the installed version with:

```powershell
python -c "import station_calibration; print(station_calibration.__version__)"
3dsc-ice-server --version
```

Manual and automatic service updates are covered in
[Deployment and Autostart](Deployment.md).
