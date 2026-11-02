# Deployment and Autostart

This page describes how to install the optional ZeroC Ice calibration server on
a Windows PC or a 64-bit Raspberry Pi and how to start it automatically at boot.

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
Ice calibration server listening on tcp -h 0.0.0.0 -p 10000
Proxy: CalibrationPhenoseederIcing:tcp -h ...
```

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
To clone using git, first install git.
```powershell
winget install --id Git.Git -e
```
Clone from the main
```powershell
git clone <repository_url> C:\3DSC\app
```
or selected branch
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
C:\3DSC\.venv\Scripts\python.exe -c "import station_calibration, Ice; print(Ice.stringVersion())"
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
Get-Service $svc
nssm status $svc
Get-Content C:\ProgramData\3DSC\logs\ice-server.err.log -Wait
Test-NetConnection <server-name> -Port 10000
```

Restart, stop, and remove:

```powershell
nssm restart $svc
nssm stop $svc
nssm remove $svc confirm
Remove-NetFirewallRule -DisplayName "3DSC Ice Server (TCP 10000)"
```

Prevent the server from sleeping:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 15
```

### Alternative: Task Scheduler

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
/opt/3dsc/.venv/bin/python -c "import Ice, cv2, numpy, scipy; print(Ice.stringVersion(), cv2.__version__)"
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

```bash
sudo systemctl stop 3dsc-ice-server
cd /opt/3dsc/app
sudo -u 3dsc git pull
sudo -u 3dsc /opt/3dsc/.venv/bin/python -m pip install .
sudo systemctl start 3dsc-ice-server
```

Uninstall:

```bash
sudo systemctl disable --now 3dsc-ice-server
sudo rm /etc/systemd/system/3dsc-ice-server.service
sudo systemctl daemon-reload
```

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
