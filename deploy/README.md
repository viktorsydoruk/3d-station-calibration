# Deployment files

This directory contains the service and automatic-update files for the two
supported production platforms. Application configuration and calibration data
stay outside the checkout.

| File | Platform | Purpose |
| --- | --- | --- |
| `linux/3dsc-ice-server.service` | Raspberry Pi | systemd unit template for the Ice server |
| `linux/3dsc-update` | Raspberry Pi | updater that follows the newest CalVer release tag |
| `linux/3dsc-update.service` | Raspberry Pi | oneshot systemd service that runs the updater |
| `linux/3dsc-update.timer` | Raspberry Pi | daily timer for the updater |
| `windows/Update-3DSC.ps1` | Windows | updater with NSSM service control, health check, and rollback |
| `windows/Register-UpdateTask.ps1` | Windows | registers the updater with Task Scheduler |

## Windows order

1. Install Python 3.13, Git, and NSSM.
2. Clone the repository to `C:\3DSC\app` and create `C:\3DSC\.venv`.
3. Install the package with the Ice extra.
4. Copy `src/station_calibration/resources/config.toml` to
   `C:\3DSC\config.toml` and set production paths, including
   `[general] procedures_root = "C:/ProgramData/3DSC/procedures"`. Create one
   `<procedures-root>/<procedure-id>/config.toml` per procedure.
5. Register the NSSM service with `--config C:\3DSC\config.toml`, then start it
   and check the log. The procedures root is read from the config, not a CLI
   argument.
6. Run `Update-3DSC.ps1 -DryRun` before enabling the scheduled task.
7. Register the task with `Register-UpdateTask.ps1`.

See [Deployment and Autostart](../docs/wiki/Deployment.md) for the full commands
and security notes.

## Raspberry Pi order

1. Install Python 3.13, Git, and `python3-zeroc-ice` from the ZeroC APT
   repository.
2. Create the `3dsc` service account and the `/opt/3dsc/app` checkout.
3. Create `/opt/3dsc/.venv` with `--system-site-packages` and install the
   package without the `[ice]` extra.
4. Create `/etc/3dsc/config.toml`, the writable output/debug directories, and
   `/var/lib/3dsc/procedures/<procedure-id>/config.toml` per procedure. Set
   `[general] procedures_root = "/var/lib/3dsc/procedures"`.
5. Copy `linux/3dsc-ice-server.service` to `/etc/systemd/system/` and edit the
   paths. The service starts with `--config /etc/3dsc/config.toml`; the
   procedures root is read from that file.
6. Enable the server unit and verify the TCP endpoint.
7. Copy the updater service and timer, then enable the timer.

See [Deployment and Autostart](../docs/wiki/Deployment.md) for the full commands
and automatic-update policy.

## Automatic-update requirements

- The checkout must have an `origin` remote and a clean working tree.
- Only annotated `vYYYY.MM.DD[.N]` tags are installed.
- The updater stops the server, checks out the tag, reinstalls the package,
  verifies `--version`, starts the service, and checks the TCP port.
- A failed update rolls back to the previous tag or commit.
- Use a maintenance window: the updater cannot detect an active calibration run.
