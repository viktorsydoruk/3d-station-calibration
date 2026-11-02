# Deployment and Autostart

This page describes how to install the optional ZeroC Ice calibration server on
a Windows PC or a 64-bit Raspberry Pi, start it automatically at boot, and
optionally keep it updated from release tags.

The folder workflow (`3dsc`) can stay an interactive tool. The Ice server is the
long-running process that receives raw camera frames and robot coordinates from
the production client.

## Deployment model

- The **server** owns the calibration folder: images, `Calibration3DPositions.csv`,
  the production TOML configuration, and writable output/debug folders.
- The **client** runs on the machine that produces the images and robot
  coordinates. It sends `addData(Point, imageData)` calls.
- The server does **not** receive the image folder over Ice. The folder is a
  deployment setting supplied on the server command line.
- The default endpoint is `tcp -h 127.0.0.1 -p 10000`. Use
  `tcp -h 0.0.0.0 -p 10000` only when a remote client must connect directly.
- The current contract has **no authentication or encryption**. Keep the port on
  a private network, allow only known client addresses in the firewall, or use an
  SSH tunnel. Do not expose it to the Internet.

## Capacity and platform notes

| Platform | Recommendation |
| --- | --- |
| Windows 10/11 or Windows Server 2022+ | Recommended production platform. Python 3.13 and the `zeroc-ice` wheel are available. |
| Raspberry Pi 5, 8 GB, 64-bit OS | Usable for smaller runs and low-rate testing. Expect much slower fits than a desktop. |
| Raspberry Pi 4 / CM4, 4 GB, 64-bit OS | Minimum practical Pi configuration. Keep the observation target low and disable debug images/plots. |
| Raspberry Pi OS 32-bit | Not recommended. Use the 64-bit image. |

The camera analysis is CPU-bound and the current server refits after every new
observation. For 500 observations this is the dominant cost. On a Pi, reduce the
target for test runs and plan for a long final run unless the server's fit
interval is exposed as a command-line option (a recommended change).

## Common preparation

### 1. Prepare the calibration folder

The folder must contain:

```text
Calibration3DPositions.csv
image_0001.tif
image_0002.tif
...
```

The CSV delimiter is `;`. The first three fields are `Xr;Yr;Zr`; a fourth field
may contain the image name. A line whose first field contains `calibration` is
treated as a comment.

### 2. Create a production configuration

The packaged default is:

```text
src/station_calibration/resources/config.toml
```

Copy it, then edit the copy. The `--config` file is currently a **complete
replacement**, not merged with the packaged defaults, so keep every section.

At minimum set:

```toml
[general]
debug = false
store_debug_images = false
load_stored_data = false

[general.files]
# Use absolute, writable paths for a service account.
output_folder = "C:/ProgramData/3DSC/output"   # Windows example
debug_folder = "C:/ProgramData/3DSC/debug"     # Windows example
# output_folder = "/var/lib/3dsc/output"       # Linux example
# debug_folder = "/var/lib/3dsc/debug"         # Linux example
```

`load_stored_data = false` is important for the Ice server: it must analyze the
frames that arrive over the wire, not reuse an old point cache.

### 3. Smoke-test from a terminal first

Always start the server manually once before installing it as a service. This
makes configuration and firewall problems visible immediately.

```powershell
3dsc-ice-server "<calibration folder>" `
  --config "<config.toml>" `
  --endpoint "tcp -h 0.0.0.0 -p 10000"
```

The server should print:

```text
Version: <package-version>
Ice calibration server listening on tcp -h 0.0.0.0 -p 10000
Proxy: CalibrationPhenoseederIcing:tcp -h ...
```

The version is generated from Git tags by `hatch-vcs`; it is not edited in
`pyproject.toml`. See
[Testing and Build](Testing-and-Build#versioning) for the release procedure.

## Windows

### 1. Install Python 3.13

Install the 64-bit Python 3.13 from python.org, or:

```powershell
winget install --id Python.Python.3.13 -e
```

Open a new terminal and verify:

```powershell
py -3.13 --version
```

### 2. Put the project on the server

Use a short, space-free path such as `C:\3DSC\app`. Avoid running the service
from a user profile or a mapped network drive.

```powershell
New-Item -ItemType Directory -Force C:\3DSC | Out-Null
# Copy or clone the project into C:\3DSC\app
```
To clone with Git, first install Git:

```powershell
winget install --id Git.Git -e
```

Clone the default branch:

```powershell
git clone <repository_url> C:\3DSC\app
```

Or clone a specific branch:

```powershell
git clone --branch <branch_name> <repository_url> C:\3DSC\app
```

### 3. Create the virtual environment and install

```powershell
py -3.13 -m venv C:\3DSC\.venv
C:\3DSC\.venv\Scripts\python.exe -m pip install --upgrade pip
Push-Location C:\3DSC\app
C:\3DSC\.venv\Scripts\python.exe -m pip install -e ".[ice]"
Pop-Location
```

Verify that both the package and Ice are importable:

```powershell
C:\3DSC\.venv\Scripts\python.exe -c "import station_calibration, Ice; print(station_calibration.__version__, Ice.stringVersion())"
C:\3DSC\.venv\Scripts\3dsc-ice-server.exe --version
C:\3DSC\.venv\Scripts\3dsc-ice-server.exe --help
```

### 4. Create writable folders and the configuration

```powershell
New-Item -ItemType Directory -Force -Path C:\ProgramData\3DSC\logs | Out-Null
New-Item -ItemType Directory -Force -Path C:\ProgramData\3DSC\output | Out-Null
New-Item -ItemType Directory -Force -Path C:\ProgramData\3DSC\debug | Out-Null

Copy-Item `
  C:\3DSC\app\src\station_calibration\resources\config.toml `
  C:\3DSC\config.toml
```

Edit `C:\3DSC\config.toml` as described in
[Common preparation](#common-preparation). Use forward slashes in TOML paths.

### 5. Run manually once

```powershell
C:\3DSC\.venv\Scripts\3dsc-ice-server.exe `
  "\\fileserver\share\station01" `
  --config "C:\3DSC\config.toml" `
  --endpoint "tcp -h 0.0.0.0 -p 10000"
```

Stop it with `Ctrl+C` after confirming that it starts and prints the proxy.

> **Service accounts and mapped drives.** A Windows service does not see `P:`
> drives mapped in your interactive session. Use a UNC path such as
> `\\fileserver\share\station01`, or run the service as an account that has the
> same drive mapping (not recommended).

### 6. Install as a Windows service with NSSM

NSSM is a small service wrapper that handles restart, stdout/stderr redirection,
and log rotation. Install it with:

```powershell
winget install --id NSSM.NSSM -e
```

Open a new PowerShell window (so `nssm.exe` is on `PATH`) and verify:

```powershell
nssm version
```

Install and configure the service:

```powershell
$svc      = "3DSC-IceServer"
$exe      = "C:\3DSC\.venv\Scripts\3dsc-ice-server.exe"
$folder   = "\\fileserver\share\station01"
$config   = "C:\3DSC\config.toml"
$endpoint = "tcp -h 0.0.0.0 -p 10000"

nssm install $svc $exe
nssm set $svc AppDirectory "C:\3DSC"
nssm set $svc AppParameters "`"$folder`" --config `"$config`" --endpoint `"$endpoint`""
nssm set $svc DisplayName "3D Station Calibration Ice Server"
nssm set $svc Description "Serves the phenoSeeder 3D station calibration over ZeroC Ice."
nssm set $svc Start SERVICE_DELAYED_AUTO_START
nssm set $svc AppStdout "C:\ProgramData\3DSC\logs\ice-server.out.log"
nssm set $svc AppStderr "C:\ProgramData\3DSC\logs\ice-server.err.log"
nssm set $svc AppRotateFiles 1
nssm set $svc AppRotateOnline 1
nssm set $svc AppRotateSeconds 86400
nssm set $svc AppRotateBytes 10485760
nssm set $svc AppExit Default Restart
nssm set $svc AppRestartDelay 5000
nssm start $svc
```

`SERVICE_DELAYED_AUTO_START` gives the network stack and SMB client time to come
up before the server tries to open a UNC path.

#### Service account

By default NSSM runs the service as `LocalSystem`. That is sufficient for a local
calibration folder. For a network share, use a dedicated domain or local account
that has read access to the images and write access to the output/debug folders:

```powershell
$svc = "3DSC-IceServer"
nssm set $svc ObjectName "DOMAIN\svc-3dsc" "PASSWORD"
nssm restart $svc
```

Alternatively, grant the computer account (`DOMAIN\SERVERNAME$`) access to the
share. Either way, the account must be able to read the UNC path.

### 7. Open the firewall (only if clients connect directly)

```powershell
New-NetFirewallRule `
  -DisplayName "3DSC Ice Server (TCP 10000)" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 10000 `
  -Action Allow `
  -Profile Domain,Private
```

Do not create a rule for the Public profile. If clients are on another subnet,
restrict the rule with `-RemoteAddress`.

### 8. Verify and operate

```powershell
$svc = "3DSC-IceServer"
Get-Service $svc
nssm status $svc
Get-Content C:\ProgramData\3DSC\logs\ice-server.err.log -Wait
Test-NetConnection <server-name> -Port 10000
```

Restart, stop, and remove:

```powershell
$svc = "3DSC-IceServer"
nssm restart $svc
nssm stop $svc
Unregister-ScheduledTask -TaskName "3DSC-IceServer-Update" -Confirm:$false -ErrorAction SilentlyContinue
nssm remove $svc confirm
Remove-NetFirewallRule -DisplayName "3DSC Ice Server (TCP 10000)"
```

Prevent the server from sleeping:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 15
```

### 9. Update the server

The application lives in `C:\3DSC\app`. The configuration is outside the
repository at `C:\3DSC\config.toml`, so pulling new code does not overwrite it.
Back it up before an update:

```powershell
Copy-Item C:\3DSC\config.toml C:\3DSC\config.toml.bak
```

Stop the service, update the checkout, reinstall the package, and start it again:

```powershell
$svc = "3DSC-IceServer"
nssm stop $svc

Push-Location C:\3DSC\app
git status --short          # must be empty; commit or stash local edits first
git pull --ff-only
C:\3DSC\.venv\Scripts\python.exe -m pip install --upgrade -e ".[ice]"
C:\3DSC\.venv\Scripts\3dsc-ice-server.exe --version
Pop-Location

nssm start $svc
nssm status $svc
Get-Content C:\ProgramData\3DSC\logs\ice-server.err.log -Tail 20
```

- `--upgrade` makes pip reinstall the project even when the version has not
  changed. If you installed without `-e`, omit `-e` from the pip command.
- Close Jupyter, debuggers, and other processes that use `C:\3DSC\.venv` before
  reinstalling; Windows locks loaded DLLs such as ZeroMQ or psutil and pip cannot
  replace them.
- For a tagged release, replace `git pull --ff-only` with
  `git fetch --tags` and `git checkout <release-tag>`.
- If the service fails after an update, check out the previous tag, reinstall
  with the same pip command, and start the service again.
- Keep `output` and `debug` paths outside `C:\3DSC\app`; an update replaces the
  application directory only.

To automate this on a schedule, see
[Automatic updates](#automatic-updates).

### Alternative autostart: Task Scheduler

If NSSM cannot be installed, create a task with **At startup**, **Run whether
user is logged on or not**, and **Run with highest privileges**. Point it at
`C:\3DSC\.venv\Scripts\3dsc-ice-server.exe` and the same arguments. Task
Scheduler does not provide the restart/rotation behavior of NSSM, so NSSM is
preferred for an unattended server.

## Raspberry Pi (64-bit)

### 1. Use Raspberry Pi OS Trixie 64-bit

Raspberry Pi OS Trixie is based on Debian 13 and ships Python 3.13, which matches
this project's `requires-python`. A 64-bit image is required for the available
`aarch64` wheels.

```bash
uname -m          # must print aarch64
python3 --version # must print Python 3.13.x
```

Update the OS:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git python3-venv python3-pip libgl1 libglib2.0-0 cifs-utils
```

`libgl1` and `libglib2.0-0` satisfy the non-headless OpenCV wheel. `cifs-utils`
is only needed when the calibration folder is on an SMB share.

### 2. Install ZeroC Ice from the ZeroC APT repository

There is **no Linux `zeroc-ice` wheel on PyPI** for 3.8.3. Do not run
`pip install ".[ice]"` on the Pi; pip would try to build Ice from source. Use the
official Debian 13 `arm64` package instead:

```bash
wget https://download.zeroc.com/ice/3.8/debian13/ice-repo-3.8_1.0.0_all.deb -O /tmp/ice-repo.deb
sudo dpkg -i /tmp/ice-repo.deb
sudo apt update
sudo apt install -y python3-zeroc-ice
python3 -c "import Ice; print(Ice.stringVersion())"
```

### 3. Install the project in a venv that can see the system Ice package

```bash
sudo mkdir -p /opt/3dsc
sudo chown "$USER":"$USER" /opt/3dsc

# Copy or clone the project to /opt/3dsc/app
cd /opt/3dsc/app

python3 -m venv --system-site-packages /opt/3dsc/.venv
/opt/3dsc/.venv/bin/python -m pip install --upgrade pip
/opt/3dsc/.venv/bin/python -m pip install .
```

The `--system-site-packages` flag is what makes the APT-installed `Ice` module
visible inside the venv. Install the project **without** the `ice` extra on
Linux.

Verify:

```bash
/opt/3dsc/.venv/bin/python -c "import station_calibration, Ice, cv2, numpy, scipy; print(station_calibration.__version__, Ice.stringVersion(), cv2.__version__)"
/opt/3dsc/.venv/bin/3dsc-ice-server --version
/opt/3dsc/.venv/bin/3dsc-ice-server --help
```

### 4. Create the service account and writable folders

```bash
sudo useradd --system --home-dir /opt/3dsc --shell /usr/sbin/nologin 3dsc
sudo chown -R 3dsc:3dsc /opt/3dsc

sudo mkdir -p /var/lib/3dsc/output /var/lib/3dsc/debug /etc/3dsc
sudo chown -R 3dsc:3dsc /var/lib/3dsc

sudo cp /opt/3dsc/app/src/station_calibration/resources/config.toml /etc/3dsc/config.toml
sudo chown root:3dsc /etc/3dsc/config.toml
sudo chmod 640 /etc/3dsc/config.toml
```

Edit `/etc/3dsc/config.toml` as described in
[Common preparation](#common-preparation). Use the Linux output/debug paths, for
example `/var/lib/3dsc/output` and `/var/lib/3dsc/debug`.

### 5. Mount the calibration folder (optional)

For a local folder, use a path such as `/srv/3dsc/station01` and skip this step.

For an SMB share, create a credentials file:

```bash
sudo install -m 600 /dev/null /etc/3dsc-cifs.credentials
sudo nano /etc/3dsc-cifs.credentials
```

```ini
username=svc-3dsc
password=CHANGE_ME
domain=EXAMPLE
```

Mount it read-only because the server only reads the images and CSV; the output
and debug folders are absolute paths under `/var/lib/3dsc`:

```bash
sudo mkdir -p /mnt/calibration
```

Add to `/etc/fstab`:

```fstab
//fileserver/share /mnt/calibration cifs credentials=/etc/3dsc-cifs.credentials,uid=3dsc,gid=3dsc,iocharset=utf8,vers=3.1.1,ro 0 0
```

Then:

```bash
sudo systemctl daemon-reload
sudo mount -a
sudo -u 3dsc ls /mnt/calibration/station01
```

The calibration folder for the service is
`/mnt/calibration/station01` in this example.

### 6. Install the systemd service

A template is provided at:

```text
deploy/linux/3dsc-ice-server.service
```

Copy it and edit the folder, config, user, and paths:

```bash
sudo cp /opt/3dsc/app/deploy/linux/3dsc-ice-server.service /etc/systemd/system/
sudo nano /etc/systemd/system/3dsc-ice-server.service
```

The important lines are:

```ini
ExecStart=/opt/3dsc/.venv/bin/3dsc-ice-server /mnt/calibration/station01 --config /etc/3dsc/config.toml --endpoint "tcp -h 0.0.0.0 -p 10000"
User=3dsc
Group=3dsc
ReadWritePaths=/var/lib/3dsc
RequiresMountsFor=/mnt/calibration
```

Remove `RequiresMountsFor=` when the calibration folder is local. If the
calibration folder itself must be writable, add it to `ReadWritePaths=`.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now 3dsc-ice-server
sudo systemctl status --no-pager 3dsc-ice-server
```

Follow logs:

```bash
sudo journalctl -u 3dsc-ice-server -f
```

Check the listening socket:

```bash
sudo ss -ltnp | grep 10000
```

### 7. Open the firewall or use an SSH tunnel

Direct connection, restricted to the plant network:

```bash
sudo apt install -y ufw
sudo ufw allow from 192.168.1.0/24 to any port 10000 proto tcp
sudo ufw enable
```

More secure: bind Ice to `127.0.0.1` and forward the port over SSH from the
client machine:

```bash
ssh -N -L 10000:127.0.0.1:10000 3dsc@<pi-address>
```

Then point the client at `127.0.0.1:10000`. The Ice traffic stays inside the SSH
tunnel.

### 8. Update and uninstall

The configuration is outside the checkout at `/etc/3dsc/config.toml`, so
`git pull` does not overwrite it. Back it up first:

```bash
sudo cp /etc/3dsc/config.toml /etc/3dsc/config.toml.bak
```

Stop the service, update the checkout, and reinstall:

```bash
sudo systemctl stop 3dsc-ice-server

sudo -u 3dsc git -C /opt/3dsc/app status --short   # must be empty
sudo -u 3dsc git -C /opt/3dsc/app pull --ff-only
sudo -u 3dsc /opt/3dsc/.venv/bin/python -m pip install --upgrade /opt/3dsc/app
sudo -u 3dsc /opt/3dsc/.venv/bin/3dsc-ice-server --version
```

If `deploy/linux/3dsc-ice-server.service` changed in the new revision, reinstall
the unit now. Preserve any site-specific paths you edited:

```bash
sudo cp /opt/3dsc/app/deploy/linux/3dsc-ice-server.service /etc/systemd/system/
sudo systemctl daemon-reload
```

If automatic updates are installed and `deploy/linux/3dsc-update.service` or
`deploy/linux/3dsc-update.timer` changed, reinstall those units as well:

```bash
sudo cp /opt/3dsc/app/deploy/linux/3dsc-update.service /etc/systemd/system/
sudo cp /opt/3dsc/app/deploy/linux/3dsc-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart 3dsc-update.timer
```

Start the service and verify it:

```bash
sudo systemctl start 3dsc-ice-server
sudo systemctl status --no-pager 3dsc-ice-server
sudo journalctl -u 3dsc-ice-server -n 30 --no-pager
```

Update the system Ice package separately when the OS repository provides a newer
version:

```bash
sudo apt update
sudo apt install --only-upgrade python3-zeroc-ice
```

For a tagged release, replace `git pull --ff-only` with `git fetch --tags` and
`git checkout <release-tag>`. To roll back, check out the previous tag, reinstall
with the same pip command, and restart the service.

To automate this on a schedule, see
[Automatic updates](#automatic-updates).

Uninstall:

```bash
sudo systemctl disable --now 3dsc-update.timer 2>/dev/null || true
sudo systemctl disable --now 3dsc-ice-server
sudo rm /etc/systemd/system/3dsc-ice-server.service
sudo rm -f /etc/systemd/system/3dsc-update.service /etc/systemd/system/3dsc-update.timer
sudo systemctl daemon-reload
```

The application, configuration, service account, and data are intentionally left
in place. Remove them only when you no longer need the calibration results:

```bash
# Review these paths before removing anything.
sudo rm -rf /opt/3dsc /etc/3dsc /var/lib/3dsc
sudo userdel 3dsc
```

## Automatic updates

Both deployment layouts include an optional updater that follows the newest
calendar-version release tag (`vYYYY.MM.DD[.N]`). It runs outside the Ice
process; the server never updates itself while it is handling requests.

The updater:

1. takes a platform lock so two updates cannot overlap,
2. refuses to run when the Git working tree has local changes,
3. fetches tags and selects the newest calendar-version tag,
4. rejects lightweight or non-CalVer tags by default,
5. stops the service,
6. checks out the tag and reinstalls the package,
7. verifies the new `3dsc-ice-server --version`,
8. starts the service and checks its TCP port,
9. rolls back to the previous tag or commit if a step fails.

> **Use a maintenance window.** The updater restarts the Ice server. It cannot
> detect whether a calibration run is in progress. Schedule it outside production
> runs, or trigger it manually when the server is idle.

Automatic updates install application releases only. They do not run OS updates
or upgrade `python3-zeroc-ice` on the Pi.

> **Tag the release before enabling the schedule.** The updater only sees pushed
> `vYYYY.MM.DD[.N]` tags. If the newest tag is older than the current checkout,
> the first run moves the server back to that tag. Create releases with
> `scripts/release.py`, which enforces a clean checkout and annotated tags; see
> [Testing and Build](Testing-and-Build#create-a-release).

### Windows automatic updates

The updater is:

```text
deploy/windows/Update-3DSC.ps1
```

It uses the paths and service name from the NSSM setup above. Open an elevated
PowerShell and run a dry run first; it fetches tags and prints the planned
change without stopping the service:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File C:\3DSC\app\deploy\windows\Update-3DSC.ps1 -DryRun
```

Register a daily task at 03:00:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File C:\3DSC\app\deploy\windows\Register-UpdateTask.ps1 `
  -Schedule Daily -Time 03:00
```

The helper creates task `3DSC-IceServer-Update`, runs it with the highest
privileges (`SYSTEM` by default), starts it when the scheduled time was missed,
and prevents overlapping instances. To use a weekly window:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File C:\3DSC\app\deploy\windows\Register-UpdateTask.ps1 `
  -Schedule Weekly -Day Sunday -Time 03:00
```

Run it now and inspect the result:

```powershell
Start-ScheduledTask -TaskName "3DSC-IceServer-Update"
Get-ScheduledTaskInfo -TaskName "3DSC-IceServer-Update"
Get-Content C:\ProgramData\3DSC\logs\update.log -Tail 50
```

Disable automatic updates:

```powershell
Unregister-ScheduledTask -TaskName "3DSC-IceServer-Update" -Confirm:$false
```

Override defaults when the installation differs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File C:\3DSC\app\deploy\windows\Update-3DSC.ps1 `
  -AppDir "D:\3DSC\app" `
  -VenvDir "D:\3DSC\.venv" `
  -ServiceName "3DSC-IceServer" `
  -HealthHost "127.0.0.1" `
  -HealthPort 10000 `
  -TagPattern "v[0-9]*"
```

Add `-RequireSignedTag` to verify the tag signature with `git tag -v` before
installing it. Add `-AllowLightweightTags` only if the repository deliberately
uses lightweight tags.

By default the scheduled task runs as `SYSTEM`. For a private repository,
configure a read-only deploy key for that account, or register the task under the
account that owns the checkout:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File C:\3DSC\app\deploy\windows\Register-UpdateTask.ps1 `
  -RunAs "DOMAIN\svc-3dsc" `
  -Schedule Daily -Time 03:00
```

The helper prompts for that account's password and stores it in Task Scheduler.
The account needs read/write access to `C:\3DSC\app` and `C:\3DSC\.venv`, plus
read-only Git credentials for the repository.

If the installation does not use the default paths, pass the same `-AppDir`,
`-VenvDir`, `-ServiceName`, `-HealthHost`, `-HealthPort`, and `-TagPattern`
values to `Register-UpdateTask.ps1`. Pass `-RequireSignedTag` or
`-AllowLightweightTags` there as well so the scheduled task applies the same tag
policy.

### Raspberry Pi automatic updates

The updater and its systemd units are:

```text
deploy/linux/3dsc-update
deploy/linux/3dsc-update.service
deploy/linux/3dsc-update.timer
```

The timer checks daily at 03:00, with up to 15 minutes of random delay. The
service runs the updater as root because it must stop and start
`3dsc-ice-server`; Git and pip commands are executed as `3dsc`.

Install and enable the timer:

```bash
sudo cp /opt/3dsc/app/deploy/linux/3dsc-update.service /etc/systemd/system/
sudo cp /opt/3dsc/app/deploy/linux/3dsc-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now 3dsc-update.timer
systemctl list-timers 3dsc-update.timer
```

Run a dry run manually:

```bash
sudo bash /opt/3dsc/app/deploy/linux/3dsc-update --dry-run
```

Run an update now and inspect the journal:

```bash
sudo systemctl start 3dsc-update.service
sudo journalctl -u 3dsc-update.service -n 80 --no-pager
```

Disable automatic updates:

```bash
sudo systemctl disable --now 3dsc-update.timer
```

Create `/etc/3dsc/update.env` to override defaults; the unit reads it when
present:

```bash
sudo install -m 640 /dev/null /etc/3dsc/update.env
sudo nano /etc/3dsc/update.env
```

```ini
APP_DIR=/opt/3dsc/app
VENV_DIR=/opt/3dsc/.venv
SERVICE_NAME=3dsc-ice-server
RUN_USER=3dsc
REMOTE=origin
TAG_PATTERN=v[0-9]*
ALLOW_LIGHTWEIGHT_TAGS=0
REQUIRE_SIGNED_TAG=0
HEALTH_HOST=127.0.0.1
HEALTH_PORT=10000
HEALTH_TIMEOUT_SECONDS=60
```

The Pi updater runs Git and pip as `3dsc`. Configure a read-only deploy key in
`/opt/3dsc/.ssh` for that user and test it before relying on the timer:

```bash
sudo -u 3dsc git -C /opt/3dsc/app fetch --tags origin
```

To change the maintenance window, add a drop-in for the installed timer:

```bash
sudo systemctl edit 3dsc-update.timer
```

```ini
[Timer]
OnCalendar=
OnCalendar=Sun *-*-* 03:00:00
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart 3dsc-update.timer
systemctl list-timers 3dsc-update.timer
```

### Update policy

- Automatic updates require a Git checkout with a configured `origin` remote; a
  copied source folder is not enough.
- Only calendar-version tags in the form `vYYYY.MM.DD[.N]` are installed.
  Unrelated `v`-prefixed tags are ignored. Legacy tags without `.N` are treated
  as revision `0`.
- Release tags must be annotated. Lightweight tags are rejected unless
  `-AllowLightweightTags` (Windows) or `ALLOW_LIGHTWEIGHT_TAGS=1` (Pi) is set.
- Set `-RequireSignedTag` or `REQUIRE_SIGNED_TAG=1` to run `git tag -v` and
  require a signature from a key trusted by the task account or `3dsc` user.
- The updater does not follow a branch, so the checkout normally ends up on a
  detached HEAD at the release tag.
- If the checkout is already at the commit of the newest release, it exits
  without restarting the service. A legacy `vYYYY.MM.DD` tag and
  `vYYYY.MM.DD.0` on the same commit count as the same release.
- Local changes cause the updater to abort. It never discards them.
- The previous tag or commit is retained and used for automatic rollback.
- The health check only verifies that the Ice TCP endpoint accepts a connection.
  It does not run a calibration.
- Restrict who can push or move release tags, and use read-only credentials on
  the server. Do not move or reuse a tag that has already been deployed.
- The Pi updater does not reinstall its own systemd units. Reinstall those files
  manually when they change in a release.

### Automatic update troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Task or timer does not run | Not enabled, or the scheduled time is outside the maintenance window | Check `Get-ScheduledTaskInfo` or `systemctl list-timers 3dsc-update.timer`. |
| `Git working tree is not clean` | Local edits or copied files inside the checkout | Commit, stash, or remove them; keep data and configuration outside the checkout. |
| `git fetch` fails or asks for credentials | Task account cannot reach the repository | Configure a read-only deploy key for `SYSTEM`/`3dsc` and test the fetch manually. |
| Windows update rolls back with `Access is denied` | Jupyter, an IDE, or a debugger still locks the venv | Close those processes before the scheduled maintenance window. |
| Update rolled back after the health check | Wrong port, bind address, or server failed to start | Match `HealthHost`/`HealthPort` to the endpoint and inspect the server log/journal. |
| `No calendar-version release tags ... match 'v[0-9]*'` | No CalVer tags were fetched | Create and push a release tag with `scripts/release.py`, then run `git fetch --tags`. |
| `Tag '...' is lightweight` | The tag was created with plain `git tag` | Recreate it as an annotated tag (`git tag -a`) and push it, or set the allow switch for a legacy repository. |

## Client connection

On a Windows client, install the project with the Ice extra:

```powershell
python -m pip install -e ".[ice]"
```

Test with the one-image CLI:

```powershell
3dsc-ice-client `
  --proxy "CalibrationPhenoseederIcing:tcp -h 192.168.1.50 -p 10000" `
  --x 12.5 --y -40.0 --z 81.2 `
  image_0001.tif
```

> The one-image CLI calls `init(None)` before sending its image. That resets the
> server session. Do not invoke the CLI once per image for a full calibration
> run. Use a long-lived client and call `init(None)` only once.

```python
from station_calibration.ice import CalibrationIceClient

proxy = "CalibrationPhenoseederIcing:tcp -h 192.168.1.50 -p 10000"
with CalibrationIceClient.connect(proxy) as client:
    client.init(None)  # once per calibration run

    for image_path, robot_xyz in images:
        client.add_image_file(image_path, robot_xyz)
        if client.is_ready():
            break

    intrinsic, intrinsic_error = client.get_intrinsic()
    extrinsic, extrinsic_error = client.get_extrinsic()
    distortion, distortion_error = client.get_distortion()
    nozzle = client.get_optimal_nozzle_position()
```

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `ModuleNotFoundError: Ice` on the Pi | venv was created without system packages | Recreate it with `python3 -m venv --system-site-packages ...`; reinstall the project. |
| `pip` tries to build `zeroc-ice` on Linux | `.[ice]` extra used on Linux | Install the project without the extra and install `python3-zeroc-ice` from the ZeroC APT repo. |
| `Config file not found` | Wrong `--config` path | Use an absolute path. |
| `Missing config section '[...]'` | The `--config` file is partial | Copy the full packaged config and edit the copy. |
| `Permission denied` for `output` or `debug` | Relative paths under a read-only share | Set absolute writable paths in `[general.files]`. |
| `Access is denied` during a Windows update | Jupyter, an IDE, or another process still uses the venv | Close it, then rerun the pip install. |
| `--version` still shows the old version | pip skipped the reinstall or the service was not restarted | Reinstall with `--upgrade`, restart the service, and check again. |
| `robot positions does not match ... images` | CSV names, patterns, or sorting | Check the CSV fourth column and `image_name_patterns`. |
| Server starts, client times out | Firewall, bind address, or long fit | Check the endpoint, firewall, and `journalctl`; increase the client timeout if the fit is slow. |
| `Ice.ObjectNotExistException` | Wrong identity or proxy | Use `CalibrationPhenoseederIcing` and the printed endpoint. |
| `Proxy does not implement CalibrationPhenoseederIcing` | Contract revision mismatch | Rebuild the client and server from the same `.ice` files and regenerate stubs. |
| Very slow on the Pi | Refit after every observation | Lower `target_observations` for tests; see the optimization recommendations. |

## Security checklist

- [ ] Bind to `127.0.0.1` and use an SSH tunnel, or bind to `0.0.0.0` with a firewall allowlist for known client IPs.
- [ ] Do not expose port 10000 to the Internet.
- [ ] Run the service as a dedicated, least-privilege account.
- [ ] Keep the calibration share read-only; write results to a local writable path.
- [ ] Protect the service account password and the SMB credentials file.
- [ ] Keep the OS, Python dependencies, and ZeroC Ice patched.
- [ ] Use read-only Git credentials for automatic updates.
- [ ] Restrict who can push or move release tags; the updater executes code as
      `SYSTEM` or root.
