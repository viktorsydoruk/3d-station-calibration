# 3D Station Calibration — Wiki

Camera and robot calibration for **phenoSeeder 3D stations**.

A white calibration sphere is moved through the working volume by the robot. For
every position the station records the robot coordinate and one image of the
sphere. From these image/coordinate pairs the package estimates:

- camera intrinsics (`fx`, `fy`, `cx`, `cy`),
- lens distortion coefficients,
- the robot-to-camera rotation and translation,
- the sphere diameter,
- the nozzle-end home position in robot coordinates.

One shared analysis/fitting engine is used by two frontends: a folder workflow
and an optional ZeroC Ice server/client.

## At a glance

| Item | Value |
| --- | --- |
| Python | 3.13 or newer |
| Package | `3dstationcalibration` |
| Version | Generated from Git tags by `hatch-vcs` |
| Core import | `station_calibration` |
| Default config | `src/station_calibration/resources/config.toml` |
| Folder command | `3dsc <folder>` |
| Ice commands | `3dsc-ice-server <folder>`, `3dsc-ice-client` |
| License | Apache-2.0 (ZeroC Ice optional, see `THIRD_PARTY_NOTICES.md`) |

## Quick start

```powershell
# install (development)
uv sync

# calibrate a folder
3dsc "P:\3Dcalibration\3D_example"

# run the optional Ice server
uv sync --extra ice
3dsc-ice-server "P:\3Dcalibration\3D_example"
```

Results are written below the calibration folder:

```text
<folder>/output/CalibrationAllPoints.dat
<folder>/output/calibration_data.yaml
<folder>/debug/
```

See [Folder Workflow](Folder-Workflow) for the input layout and
[Files and Outputs](Files-and-Outputs) for the file formats.

## Documentation

| Page | Contents |
| --- | --- |
| [Installation](Installation) | Requirements, optional extras, entry points |
| [Deployment and Autostart](Deployment) | Windows service, Raspberry Pi systemd, automatic updates, firewall, security |
| [Folder Workflow](Folder-Workflow) | Input layout, commands, cache reuse |
| [Configuration](Configuration) | Every TOML key, defaults, overrides |
| [Architecture](Architecture) | Package layout and shared-engine data flow |
| [Image Analysis](Image-Analysis) | Sphere detection, background, blur sigma |
| [Calibration Model](Calibration-Model) | Frames, parameters, fit, outliers, uncertainties |
| [Home and Nozzle](Home-and-Nozzle) | Robot home shift and nozzle-end position |
| [Session and Readiness](Session-and-Readiness) | Fit policy, stop policy, result objects |
| [Python API](Python-API) | Library usage and public exports |
| [Ice Interface](Ice-Interface) | Server, client, contracts, deployment |
| [Files and Outputs](Files-and-Outputs) | Point cache, YAML result, debug images |
| [Testing and Build](Testing-and-Build) | pytest, uv lock, wheel and sdist |
| [Troubleshooting](Troubleshooting) | Common errors and diagnostics |

## Conventions

- Paths are relative to the repository root unless stated otherwise.
- Shell examples use PowerShell on Windows and `bash` for Linux/Raspberry Pi.
- Links omit the `.md` extension so they work both in the repository and when
  the contents of `docs/wiki/` are published as a GitHub wiki (`_Sidebar.md` is
  picked up automatically by GitHub wikis).
