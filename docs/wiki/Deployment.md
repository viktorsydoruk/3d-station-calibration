# Deployment and Autostart

This page describes how to install the optional ZeroC Ice calibration server on
a Windows PC or a 64-bit Raspberry Pi, start it automatically at boot, and
optionally keep it updated from release tags.

The folder workflow (`3dsc`) can stay an interactive tool. The Ice server is the
long-running process that receives raw camera frames and robot coordinates from
the production client.

## Deployment model

- The **client** runs on the machine that produces the images and robot
  coordinates. It sends `addData(Point, imageData)` calls.
- The **server** receives each frame and robot position over Ice. It does not
  read images or `Calibration3DPositions.csv` from the procedures root.
- The **procedures root** is configured only in the server TOML file as
  `[general] procedures_root`. It must be an absolute path and is the base for
  every procedure folder and session archive. It may be a UNC path when the
  archive must live on a file server.
- `output_folder` and `debug_folder` are resolved relative to `<date>/data` by
  default. Set absolute local paths in the procedure config to keep plots,
  debug images, and intermediate output off a network share.
- NSSM writes server logs to `C:\ProgramData\3DSC\logs`; they are never stored
  under `procedures_root`.
- Each procedure has a complete default config at
  `<procedures-root>/<procedure-id>/config.toml`. The client selects a procedure
  with `init(procedureId)`; `init` creates
  `<procedures-root>/<procedure-id>/<YYYYMMDD_HHMM>/` with a merged
  `config.toml` and a `data` folder.
- When `archive_sessions = true` (the default), every Ice session is archived
  directly in `<date>/data`. The archive contains TIFF frames at the source
  dtype and bit depth, `Calibration3DPositions.csv`,
  `calibration_result.yaml`, and `session.yaml`.
- The production TOML configuration is supplied with the required `--config`;
  it is not part of the Ice wire contract.
- The default endpoint is `tcp -h 127.0.0.1 -p 10000`. Use
  `tcp -h 0.0.0.0 -p 10000` only when a remote client must connect directly.
- The current contract has **no authentication or encryption**. Keep the port on
  a private network, allow only known client addresses in the firewall, or use an
  SSH tunnel. Do not expose it to the Internet.

The file inventory and install order for both platforms are summarized in
`deploy/README.md`.

### Session archive

`init` creates a folder named `YYYYMMDD_HHMM` immediately. If another session
starts in the same minute, `_01`, `_02`, and so on are appended:

```text
<procedures-root>/<procedure-id>/
├─ config.toml                         procedure default
├─ 20261103_1542/
│  ├─ config.toml                     merged config used for this session
│  └─ data/
│     ├─ Calibration3DPositions.csv
│     ├─ image_0001.tif
│     ├─ image_0002.tif
│     ├─ ...
│     ├─ calibration_result.yaml
│     └─ session.yaml
└─ 20261104_0810/
   ├─ config.toml
   └─ data/
      └─ ...
```

The CSV uses the folder-workflow format `Xr;Yr;Zr;image_name`, so an archived
session can be re-analyzed later with an updated fitting procedure. The date
`config.toml` is a complete copy of the settings used for that run. Archived
frames keep the dtype and bit depth received over Ice and are written with Adobe
Deflate compression; wider frames are no longer rescaled to 8 bit per frame.
Boolean frames are stored as `uint8` because TIFF has no boolean sample type.
For example:

```powershell
3dsc "C:\ProgramData\3DSC\procedures\1\20261103_1542\data" `
  --config "C:\ProgramData\3DSC\procedures\1\20261103_1542\config.toml"
```

Set `archive_sessions = false` in `[general]` if disk space is more important
than replayability.

> **Disk use.** With Adobe Deflate, a 500-frame 5 MP 8-bit session is about
> 0.9-1.0 GB on disk. A 16-bit session is data-dependent: roughly 2.7 GB when
> the signal uses 12 bits and sensor noise is modest, up to about 3.9 GB for
> full 16-bit noise, and about 5 GB if the pixels are incompressible. Monitor
> free space on the procedures root for the TIFF archive and on the local disk
> for `output` and `debug` when they are redirected. Adjust
> `target_observations` or disable archiving if necessary.

### Network archive with local output and debug

When the captured frames must be stored on a file server, set `procedures_root`
to a UNC path in the **server** config:

```toml
[general]
procedures_root = '\\ibg2fs6\phenoseed$\3DSC\procedures'
```

Use single quotes so the backslashes stay literal. Do not use a mapped drive
letter: a Windows service cannot see user drive mappings. The server rejects a
missing or inaccessible root at startup.

> **TOML escaping.** In a double-quoted TOML string, every backslash must be
> doubled. A path such as
> `procedures_root = "\\ibg2fs6\phenoseed$\3DSC\procedures"` fails with
> `tomllib.TOMLDecodeError: Unescaped '\' in a string`. Use a single-quoted
> literal string or forward slashes. See
> [Windows paths in TOML](Configuration#windows-paths-in-toml).

Logs are already local because NSSM writes them to `C:\ProgramData\3DSC\logs`.
To keep plots, debug images, and intermediate output off the share, set absolute
local paths in **each procedure config**
(`<procedures-root>/<procedure-id>/config.toml`):

```toml
[general]
archive_sessions = true
debug = false
store_debug_images = false

[general.files]
output_folder = "C:/ProgramData/3DSC/output/1"
debug_folder = "C:/ProgramData/3DSC/debug/1"
```

Edit these keys in the complete procedure config; do not reduce the file to this
snippet. `output_folder` and `debug_folder` are normally relative to the session
`data` folder. An absolute path overrides that base, so they stay on the local
disk even when `procedures_root` is a UNC path. Use a distinct folder per
procedure to avoid mixing sessions. `debug_folder` is still created and used for
failure images even when `debug` and `store_debug_images` are false.

The network session remains self-contained for replay:

```text
\\ibg2fs6\phenoseed$\3DSC\procedures\1\20261105_1234\
├─ config.toml
└─ data\
   ├─ Calibration3DPositions.csv
   ├─ image_0001.tif
   ├─ ...
   ├─ calibration_result.yaml
   └─ session.yaml
```

```powershell
3dsc "\\ibg2fs6\phenoseed$\3DSC\procedures\1\20261105_1234\data" `
  --config "\\ibg2fs6\phenoseed$\3DSC\procedures\1\20261105_1234\config.toml"
```

> **Per-date isolation.** Absolute `output_folder` and `debug_folder` values are
> shared by all sessions of that procedure. If you need separate folders per
> date, keep them relative and accept that they will also be written below the
> network `procedures_root`.

## Several procedures on one server

Use one server process when only one procedure is calibrated at a time. Each
procedure still has its own default configuration and session folders. A missing
procedure folder/config is created on its first `init`:

```text
C:\ProgramData\3DSC\
└─ procedures\
   ├─ 1\
   │  ├─ config.toml
   │  └─ 20261103_1542\
   │     ├─ config.toml
   │     └─ data\
   ├─ 2\
   │  ├─ config.toml
   │  └─ 20261104_0810\
   │     ├─ config.toml
   │     └─ data\
   └─ 3\
      └─ config.toml
```

Set the root in the server config:

```toml
[general]
procedures_root = "C:/ProgramData/3DSC/procedures"
```

Then start the server with only that config:

```powershell
3dsc-ice-server `
  --config "C:\3DSC\config.toml" `
  --endpoint "tcp -h 0.0.0.0 -p 10000"
```

If a procedure `config.toml` is missing, `init` creates the procedure folder and
copies the packaged default there. Pre-create the folder and copy the packaged
`config.toml` when you want camera-specific defaults before the first run. Each
procedure config is a complete TOML replacement. Procedure IDs are integers; the
folder name is the decimal value without zero padding, so `procedureId = 1` maps
to `<procedures-root>/1/`.

The client tells the server which procedure is active and may supply an
absolute server-side override config for that run:

```text
init(1)
addData(...)
...
getIntrinsic()
getExtrinsic()
getDistortion()
finish()        # or abort() to discard the live session
```

`init` returns the date folder. The optional override is recursively merged over
the procedure default: tables merge recursively; scalar values and arrays are
replaced. For a procedure created by that `init`, the override is also stored in
the new procedure default. For an existing procedure, it applies only to that
run. The merged result is written to `<date>/config.toml`.

The server rejects `init(2)` while procedure `1` has received images, is not
ready, and has not been finished. Call `finish()` to force a final result or
`abort()` to discard the live session, then select the next procedure. Once the session is ready, or before any
image has arrived, the next procedure may also be selected. Retrieve the results
before switching; the live session is reset, although the archive remains on
disk. Re-selecting the same procedure resets it and starts a new date folder.

For central deployment on Linux, the equivalent systemd command is:

```ini
ExecStart=/opt/3dsc/.venv/bin/3dsc-ice-server --config /etc/3dsc/config.toml --endpoint "tcp -h 0.0.0.0 -p 10000"
```

Use one process per physical station only when calibrations may overlap or when
stations need independent restarts, versions, or camera SDKs.

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

### 1. Prepare the procedures root

Create the writable root that will contain the procedure folders, for example
`C:\ProgramData\3DSC\procedures`, a UNC path such as
`\\server\share\3DSC\procedures`, or `/var/lib/3dsc/procedures`. In Ice mode this
is not an image input folder: images and robot positions arrive over Ice. The
server creates each session's date folder below the selected procedure folder.
Use a UNC path when the archive must live on a file server; see
[Network archive with local output and debug](#network-archive-with-local-output-and-debug).

You do not have to create procedure folders in advance: the first `init` for a
procedure creates `<procedures-root>/<procedure-id>/` and copies the packaged
default config there. Auto-created files use the packaged defaults, so pre-create
and edit them if you want production or camera-specific values before the first
run:

```text
C:\ProgramData\3DSC\procedures\1\config.toml
C:\ProgramData\3DSC\procedures\2\config.toml
```

If you also use the folder workflow (`3dsc`) on this machine, that workflow still
needs its own folder with images and `Calibration3DPositions.csv`. Keep the two
workflows separate unless you intentionally want to re-analyze an archived
session.

The CSV delimiter and image-name rules are only relevant to the folder workflow;
see [Folder Workflow](Folder-Workflow).

### 2. Create a production configuration

The packaged default is:

```text
src/station_calibration/resources/config.toml
```

Copy it, then edit the copy. The server config must set the absolute procedures
root:

```toml
[general]
# Local archive
procedures_root = "C:/ProgramData/3DSC/procedures"

# Network archive alternative. Single quotes keep the backslashes literal.
# procedures_root = '\\ibg2fs6\phenoseed$\3DSC\procedures'
```

The server only reads `procedures_root` from this file. The same file can also
serve as the complete runtime configuration for the folder workflow. Each
procedure default config is a separate complete TOML file. `procedures_root` is
server-only and is ignored in a procedure config. Auto-created procedure configs
start from the packaged defaults; pre-create and edit them if you need the
production values below. At minimum set:

```toml
[general]
debug = false
store_debug_images = false
archive_sessions = true
load_stored_data = false

[general.files]
# Use absolute, writable paths for a service account. Absolute local paths keep
# output/debug off a network procedures root.
output_folder = "C:/ProgramData/3DSC/output/1"   # Windows example
debug_folder = "C:/ProgramData/3DSC/debug/1"     # Windows example
# output_folder = "/var/lib/3dsc/output"         # Linux example
# debug_folder = "/var/lib/3dsc/debug"           # Linux example
```

Use a distinct local output/debug folder per procedure. See
[Network archive with local output and debug](#network-archive-with-local-output-and-debug)
when `procedures_root` is a UNC path.

`load_stored_data = false` is important for the Ice server: it must analyze the
frames that arrive over the wire, not reuse an old point cache.
`archive_sessions = true` keeps the image/CSV archive in each session's `data`
folder for later re-analysis; set it to `false` only if you do not need that
record.

### 3. Smoke-test from a terminal first

Always start the server manually once before installing it as a service. This
makes configuration and firewall problems visible immediately.

```powershell
3dsc-ice-server `
  --config "<config.toml>" `
  --endpoint "tcp -h 0.0.0.0 -p 10000"
```

The server should print:

```text
3D station calibration Ice server <package-version>
Endpoint: tcp -h 0.0.0.0 -p 10000
Identity: CalibrationPhenoseederIcing
Procedures root: <absolute-path>
Press Ctrl+C to stop.
```

The version is generated from Git tags by `hatch-vcs`; it is not edited in
`pyproject.toml`. See
[Testing and Build](Testing-and-Build#versioning) for the release procedure.

## Windows

> The examples use the default port `10000`. Replace it with your site port
> everywhere: NSSM `--endpoint`, firewall rule, updater `-HealthPort`, scheduled
> task, and client proxy. For the FZJ deployment the port is `30020`.

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

# Local procedures root. Skip this when procedures_root is a UNC path.
New-Item -ItemType Directory -Force -Path C:\ProgramData\3DSC\procedures | Out-Null

# Per-procedure local output/debug folders used in the example below.
New-Item -ItemType Directory -Force -Path C:\ProgramData\3DSC\output\1 | Out-Null
New-Item -ItemType Directory -Force -Path C:\ProgramData\3DSC\debug\1 | Out-Null

Copy-Item `
  C:\3DSC\app\src\station_calibration\resources\config.toml `
  C:\3DSC\config.toml
```

Edit `C:\3DSC\config.toml` as described in
[Common preparation](#common-preparation). Set
`procedures_root = "C:/ProgramData/3DSC/procedures"` for a local archive, or a
UNC path such as
`procedures_root = '\\ibg2fs6\phenoseed$\3DSC\procedures'` when the session
archive must live on a file server. For a network root, create the folder on the
share instead of locally and give the service account write access to it. Keep
`C:\ProgramData\3DSC\output` and `debug` local and set them as
absolute paths in the procedure config; see
[Network archive with local output and debug](#network-archive-with-local-output-and-debug).

The first `init` creates
`<procedures-root>\<procedure-id>\config.toml` from the packaged default. To set
camera-specific values before first use, pre-create that procedure folder and
config. Use forward slashes or single-quoted strings for Windows paths in TOML.

### 5. Run manually once

```powershell
C:\3DSC\.venv\Scripts\3dsc-ice-server.exe `
  --config "C:\3DSC\config.toml" `
  --endpoint "tcp -h 0.0.0.0 -p 10000"
```

Stop it with `Ctrl+C` after confirming that it starts and prints the procedures
root.

> **Procedures root, not an input folder.** The Ice server does not read images
> from this path. It creates the procedure session folders and writes the
> archive there. A local path is recommended unless the archive must live on a
> file server. For a UNC path, give the service account write permission and set
> absolute local `output_folder`/`debug_folder` paths in the procedure config to
> keep output and debug data off the share.

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

> Run this block only for a first install. If the service already exists,
> `nssm install` fails with `The specified service already exists`; skip that
> line, run the `nssm set` lines, then `nssm restart`.

```powershell
$svc      = "3DSC-IceServer"
$exe      = "C:\3DSC\.venv\Scripts\3dsc-ice-server.exe"
$config   = "C:\3DSC\config.toml"
$endpoint = "tcp -h 0.0.0.0 -p 10000"

nssm install $svc $exe
nssm set $svc AppDirectory "C:\3DSC"
# Note the backslash before each backtick-escaped quote.
nssm set $svc AppParameters "--config \`"$config\`" --endpoint \`"$endpoint\`""
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

> **Quote the endpoint value.** Windows PowerShell 5.1 strips embedded double
> quotes when it calls a native program. The backslash before each
> backtick-escaped quote preserves them, so NSSM stores
> `--config "C:\3DSC\config.toml" --endpoint "tcp -h 0.0.0.0 -p 10000"`.
> Without the backslash, NSSM stores the values without quotes, and the server
> parses `-h` as its own option instead of as part of the endpoint.
>
> Verify the stored value:
>
> ```powershell
> nssm get $svc AppParameters
> ```
>
> The output must contain the quotes around both the config path and the
> endpoint string.

If `nssm start` reports `SERVICE_PAUSED`, the service is not healthy: the
application is exiting and NSSM is restarting it. Stop the service and read the
application log before changing anything else:

```powershell
nssm stop $svc
Get-Content C:\ProgramData\3DSC\logs\ice-server.err.log -Tail 50
Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='nssm'} -MaxEvents 20
```

Common causes are a TOML parse error, a missing or unwritable UNC procedures
root, or another process already using the port.

The procedures root is not a service argument; it is read from
`[general] procedures_root` in `$config`.

`SERVICE_DELAYED_AUTO_START` gives the network stack and SMB client time to come
up if you intentionally archive to a UNC path.

#### Service account

By default NSSM runs the service as `LocalSystem`. That is sufficient for a local
procedures root. For a network archive, use a dedicated **domain** account,
because a mapped drive letter is not visible to a service and `LocalSystem`
authenticates to the share as the computer account (`DOMAIN\SERVERNAME$`).

The account needs:

- `Change` on the share and `Modify` on `\\server\share\...\procedures`
- `Modify` on the local `C:\ProgramData\3DSC\output` and `debug` folders
- read/execute access to `C:\3DSC\app` and `C:\3DSC\.venv`
- the `Log on as a service` right

Stop the service, then set the account and password:

```powershell
$svc  = "3DSC-IceServer"
$user = "DOMAIN\svc-3dsc"

$secure = Read-Host "Password for $user" -AsSecureString
$plain  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
)

nssm stop $svc
nssm set $svc ObjectName $user $plain
nssm get $svc ObjectName
Get-CimInstance Win32_Service -Filter "Name='$svc'" |
  Select-Object Name, StartName, State
```

`StartName` must show the account. The password is stored by Windows as a
service secret, not in `config.toml`.

Grant the account access on the file server. Run this there in an elevated
PowerShell, replacing the share name if needed:

```powershell
$user  = "DOMAIN\svc-3dsc"
$share = Get-SmbShare -Name "phenoseed$"

Grant-SmbShareAccess -Name $share.Name -AccountName $user `
  -AccessRight Change -Force

icacls (Join-Path $share.Path "3DSC") `
  /grant "${user}:(OI)(CI)M" /T
```

Grant access to the local output/debug folders and the application on the 3DSC
server:

```powershell
$user = "DOMAIN\svc-3dsc"

# Use the actual paths from [general.files] in the procedure config.
icacls "C:\ProgramData\3DSC\output" /grant "${user}:(OI)(CI)M" /T
icacls "C:\ProgramData\3DSC\debug"  /grant "${user}:(OI)(CI)M" /T

icacls "C:\3DSC\app"  /grant "${user}:(OI)(CI)RX" /T
icacls "C:\3DSC\.venv" /grant "${user}:(OI)(CI)RX" /T
```

If the venv uses a per-user Python installation under
`C:\Users\<user>\AppData\Local\Programs\Python`, grant the service account
read/execute on that base Python directory too, or install Python system-wide.

NSSM normally grants `Log on as a service` automatically when `ObjectName` is
set. If the service fails with error `1069`, grant it explicitly in
`secpol.msc` or through domain policy.

Alternatively, grant the computer account (`DOMAIN\SERVERNAME$`) access to the
share and keep `LocalSystem`. Either way, the account must be able to read and
write the UNC procedures root.

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

Restart the service:

```powershell
$svc = "3DSC-IceServer"
nssm restart $svc
```

Stop it:

```powershell
nssm stop $svc
```

Remove it only when uninstalling:

```powershell
$svc = "3DSC-IceServer"
nssm stop $svc
Unregister-ScheduledTask -TaskName "3DSC-IceServer-Update" -Confirm:$false -ErrorAction SilentlyContinue
nssm remove $svc confirm
Remove-NetFirewallRule -DisplayName "3DSC Ice Server (TCP 10000)"
```

> Do not run the remove block during a normal update. It deletes the service,
> the scheduled update task, and the firewall rule. The update steps below
> expect the service to exist.

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
Get-Service $svc          # must exist; if this fails, reinstall with step 6
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

- If `Get-Service $svc` fails, the service was removed. Reinstall it with step 6
  before continuing; otherwise `nssm stop` and `nssm start` fail with
  `OpenService(): The specified service is not an installed service`.
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
sudo apt install -y git python3-venv python3-pip libgl1 libglib2.0-0
```

`libgl1` and `libglib2.0-0` satisfy the non-headless OpenCV wheel.

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

sudo mkdir -p /var/lib/3dsc/output /var/lib/3dsc/debug /var/lib/3dsc/procedures /etc/3dsc
sudo chown -R 3dsc:3dsc /var/lib/3dsc

sudo cp /opt/3dsc/app/src/station_calibration/resources/config.toml /etc/3dsc/config.toml
sudo chown root:3dsc /etc/3dsc/config.toml
sudo chmod 640 /etc/3dsc/config.toml
```

Edit `/etc/3dsc/config.toml` as described in
[Common preparation](#common-preparation). Set
`procedures_root = "/var/lib/3dsc/procedures"` and use the Linux output/debug
paths, for example `/var/lib/3dsc/output` and `/var/lib/3dsc/debug`. The first
`init` creates `/var/lib/3dsc/procedures/<procedure-id>/config.toml` from the
packaged default. To set camera-specific values before first use, create the
procedure folder, copy the packaged config there, and edit it as the `3dsc`
service account.

### 5. Prepare the procedures root

The Ice server creates each session's date folder below the selected procedure
folder. The `/var/lib/3dsc/procedures` folder created above is the procedures
root for this example; procedure 1 uses `/var/lib/3dsc/procedures/1`, which is
created on the first `init` if it does not exist.

The archived `Calibration3DPositions.csv` and TIFF frames are written below
`/var/lib/3dsc/procedures/1/<date>/data`. Images and robot positions arrive over
Ice, so no SMB mount is required for the Ice server.

If you also use the folder workflow on this machine, keep its image/CSV folder
separate and see [Folder Workflow](Folder-Workflow).

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
ExecStart=/opt/3dsc/.venv/bin/3dsc-ice-server --config /etc/3dsc/config.toml --endpoint "tcp -h 0.0.0.0 -p 10000"
User=3dsc
Group=3dsc
ReadWritePaths=/var/lib/3dsc
```

`ReadWritePaths=/var/lib/3dsc` covers the procedures root and the archived
sessions below it.

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

> Pass `-HealthPort` when the service is not on the default port `10000`.
> Otherwise the updater's TCP health check fails and rolls the update back. For
> this deployment use `-HealthPort 30020`.
>
> If registration fails with `Join-Path ... Parameter "Path" ... empty string`,
> pass the updater explicitly:
> `-Updater C:\3DSC\app\deploy\windows\Update-3DSC.ps1`. Current versions of the
> script resolve this path automatically.

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

A successful run ends with `Update complete: ...` and `LastTaskResult = 0`.
Verify the installed build and endpoint independently:

```powershell
C:\3DSC\.venv\Scripts\3dsc-ice-server.exe --version
Get-Service 3DSC-IceServer

$healthPort = 30020  # use the configured -HealthPort
Get-NetTCPConnection -LocalPort $healthPort -State Listen
```

`hatch-vcs` normalizes the calendar tag for PEP 440: tag `v2026.11.06.0`
installs as package version `2026.11.6.0`. Compare the tag and commit in
`update.log` with `--version`; do not expect the strings to be identical.

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
configure read-only Git credentials for that account (an HTTPS deploy token or
an SSH deploy key), or register the task under the account that owns the
checkout:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File C:\3DSC\app\deploy\windows\Register-UpdateTask.ps1 `
  -RunAs "DOMAIN\svc-3dsc" `
  -Schedule Daily -Time 03:00
```

The helper prompts for that account's password and stores it in Task Scheduler.
The account needs read/write access to `C:\3DSC\app` and `C:\3DSC\.venv`, plus
read-only Git credentials for the repository.

#### Git credentials for the scheduled task

The update task and the Ice service can run as different accounts. The NSSM
service account is only used at runtime; the scheduled task runs `git` and `pip`
as its own account, `SYSTEM` by default. `SYSTEM` does not use the interactive
user's Git Credential Manager store, so an HTTPS checkout can fail with:

```text
fatal: could not read Username for 'https://gitlab.fz-juelich.de': terminal prompts disabled
```

The updater sets `GIT_TERMINAL_PROMPT=0` and `GCM_INTERACTIVE=Never`, so it
fails immediately instead of opening a credential prompt. Check both accounts
instead of assuming they are the same:

```powershell
Get-CimInstance Win32_Service -Filter "Name='3DSC-IceServer'" |
  Select-Object Name, StartName

(Get-ScheduledTask -TaskName "3DSC-IceServer-Update").Principal |
  Format-List UserId, LogonType
```

Grant the credential file to the account that actually runs `git`, not to the
service account.

**HTTPS deploy token**

Create a GitLab deploy token with the `read_repository` scope. URL-encode
characters such as `@`, `:`, `/`, and `%` if they occur in the token username or
value. Write it to a credential file:

```powershell
$tokenUser = "REPLACE_WITH_DEPLOY_TOKEN_USERNAME"
$token     = "REPLACE_WITH_DEPLOY_TOKEN"

Set-Content -LiteralPath C:\3DSC\.git-credentials `
  -Value "https://${tokenUser}:${token}@gitlab.fz-juelich.de" `
  -NoNewline -Encoding ascii
```

Restrict the file to `SYSTEM` and administrators. Use well-known SIDs instead of
localized group names such as `Administrators` or `Administratoren`:

```powershell
icacls C:\3DSC\.git-credentials /inheritance:r
icacls C:\3DSC\.git-credentials /grant:r "*S-1-5-18:(R)" "*S-1-5-32-544:(F)"
```

`S-1-5-18` is `SYSTEM`; `S-1-5-32-544` is the built-in Administrators group. A
UAC-filtered administrator token does not receive the Administrators grant
automatically, so run the interactive fetch test from an elevated PowerShell or
grant your own account temporary read access. If the task is registered with
`-RunAs`, grant that exact account read access too:

```powershell
icacls C:\3DSC\.git-credentials /grant:r "DOMAIN\svc-3dsc:(R)"
```

Use the real machine or domain name from `StartName`/`UserId`. A typo such as
`W2W8` instead of `W2K8` produces
`Zuordnungen von Kontennamen und Sicherheitskennungen wurden nicht durchgeführt`
(`account name and security ID mappings were not performed`).

Configure the checkout to use the file and reset inherited helpers:

```powershell
Set-Location C:\3DSC\app

# The final "" is intentional. cmd.exe preserves the empty argument.
cmd /c "git config --local --replace-all credential.helper """

git config --local --add credential.helper "store --file=C:/3DSC/.git-credentials"
git config --local --get-all credential.helper
```

Windows PowerShell 5.1 drops an empty `""` argument when it calls a native
program. Running `git config --local --replace-all credential.helper ""`
directly fails with `wrong number of arguments` or leaves the inherited helper
active. The `cmd.exe` form above stores an empty first entry.

The output must contain an empty line before the `store` entry:

```text

store --file=C:/3DSC/.git-credentials
```

The empty entry resets inherited helpers, including Git Credential Manager. If
it is missing, `git fetch` can still call the interactive helper first and fail
with `terminal prompts disabled`.

Test the non-interactive path before relying on the schedule:

```powershell
$env:GIT_TERMINAL_PROMPT = "0"
git fetch --tags --prune --prune-tags origin
```

Then start the scheduled task and inspect
`C:\ProgramData\3DSC\logs\update.log`. The task itself is the definitive test
because it runs under its own account, not your interactive PowerShell session.

Protect the credential file and rotate the token when necessary. Use a
read-only deploy token; do not store a personal access token with write access on
the server.

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
| `git fetch` fails or asks for credentials | Task account cannot reach the repository | Configure a read-only deploy token or key for `SYSTEM`/`3dsc` and test the fetch manually. |
| `fatal: could not read Username for 'https://...': terminal prompts disabled` | The task account has no non-interactive Git credentials, or the inherited Credential Manager helper still runs first | Configure the credential file and the empty `credential.helper` reset in [Git credentials for the scheduled task](#git-credentials-for-the-scheduled-task), then test with `GIT_TERMINAL_PROMPT=0`. |
| `git config ... credential.helper ""` reports `wrong number of arguments` | Windows PowerShell 5.1 dropped the empty argument | Use the `cmd.exe` form in [Git credentials for the scheduled task](#git-credentials-for-the-scheduled-task), then verify with `git config --local --get-all credential.helper`. |
| `icacls` reports `Administrators: ... mappings were not performed` | Localized Windows group name | Use the SID `*S-1-5-32-544` for Administrators. |
| `icacls` reports `<account>: ... mappings were not performed` | Wrong machine, domain, or account name | Read the exact `StartName` from the service and `UserId` from the scheduled task, then use that value. |
| `Zuordnungen von Kontennamen und Sicherheitskennungen wurden nicht durchgeführt` | German Windows: localized group name or wrong account | Use `*S-1-5-32-544` for Administrators and the exact account from `StartName`/`UserId`. |
| `LastTaskResult` is not `0` after an update | The updater failed before or after the health check | Read `C:\ProgramData\3DSC\logs\update.log` and the rows above; the task returns the updater's exit code. |
| Windows update rolls back with `Access is denied` | Jupyter, an IDE, or a debugger still locks the venv | Close those processes before the scheduled maintenance window. |
| Update rolled back after the health check | Wrong port, bind address, or server failed to start | Match `HealthHost`/`HealthPort` to the endpoint and inspect the server log/journal. |
| `No calendar-version release tags ... match 'v[0-9]*'` | No CalVer tags were fetched | Create and push a release tag with `scripts/release.py`, then run `git fetch --tags`. |
| `Tag '...' is lightweight` | The tag was created with plain `git tag` | Recreate it as an annotated tag (`git tag -a`) and push it, or set the allow switch for a legacy repository. |

## Client connection

On a Windows client, install the project with the Ice extra:

```powershell
python -m pip install -e ".[ice]"
```

> Install the client from the same release tag as the server. `finish()` and
> `abort()` require both the new server build and the regenerated client stubs;
> an older client package will not expose them.

Test with the one-image CLI:

```powershell
3dsc-ice-client `
  --proxy "CalibrationPhenoseederIcing:tcp -h 192.168.1.50 -p 10000" `
  --procedure-id 1 `
  --x 12.5 --y -40.0 --z 81.2 `
  image_0001.tif
```

> The one-image CLI calls `init(1)` before sending its image. That starts a new
> date folder. Do not invoke the CLI once per image for a full calibration run.
> Use a long-lived client and call `init(1)` only once.

```python
from station_calibration.ice import CalibrationIceClient

proxy = "CalibrationPhenoseederIcing:tcp -h 192.168.1.50 -p 10000"
with CalibrationIceClient.connect(proxy) as client:
    session_folder = client.init(1)  # once per calibration run

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
| `SERVICE_PAUSED` when starting the NSSM service | The application exits immediately and NSSM is in its restart delay | Check `ice-server.err.log` and the `nssm` Application events. Common causes: TOML error, share permission, port conflict. |
| `CreateService(): The specified service already exists` | `nssm install` was run for an existing service | Skip install; use `nssm set` and `nssm restart`, or `nssm remove <svc> confirm` first. |
| `OpenService(): The specified service is not an installed service` | The NSSM service was removed, for example by running the uninstall block during an update | Reinstall the service with step 6; the update steps expect it to exist. |
| `Join-Path ... Parameter "Path" ... empty string` when registering the update task | `$PSScriptRoot` is empty in that PowerShell host | Pass `-Updater C:\3DSC\app\deploy\windows\Update-3DSC.ps1` explicitly, or update to the fixed script. |
| `scipy` import fails after an update (`DLL load failed`, `_uarray`, or truncated import traceback) | Pip replaced DLLs while another process used the venv, or the environment is inconsistent | Stop all processes using `C:\3DSC\.venv`, then force-reinstall `numpy` and `scipy`; recreate the venv if it persists. |
| `server config file not found` | Wrong `--config` path | Use an absolute path. |
| Service ignores `--endpoint` or exits with argparse help | NSSM `AppParameters` lost its embedded quotes | Use the backslash-backtick form in step 6 and verify with `nssm get $svc AppParameters`. |
| `missing required setting 'procedures_root'` | Server config lacks the procedures root | Add `procedures_root = "<absolute path>"` under `[general]`. |
| `procedures root does not exist` | Typo, missing directory, or offline share | Create the directory or correct `[general] procedures_root`. |
| `PermissionError: [WinError 5]` on `\\...\procedures` | Service account lacks share/NTFS access | Grant `Change`/`Modify` to the NSSM account; mapped drives do not work for services. |
| `could not write archived image` | Share full, offline, or no write access | Check free space and write permission on the procedures root. |
| Cannot create the procedure folder/config | The service account cannot write under the procedures root | Give it write access to `<procedures-root>` and restart the server. |
| `Unescaped '\' in a string` | Windows path in a double-quoted TOML string | Use single quotes or forward slashes; see [Windows paths in TOML](Configuration#windows-paths-in-toml). |
| `Missing config section '[...]'` | A runtime TOML file is partial | Copy the full packaged config and edit the copy. |
| `Permission denied` for `output` or `debug` | Relative paths under a read-only or network share | Set absolute writable local paths in `[general.files]`. |
| `Access is denied` during a Windows update | Jupyter, an IDE, or another process still uses the venv | Close it, then rerun the pip install. |
| `--version` still shows the old version | pip skipped the reinstall or the service was not restarted | Reinstall with `--upgrade`, restart the service, and check again. |
| `robot positions does not match ... images` | CSV names, patterns, or sorting | Check the CSV fourth column and `image_name_patterns`. |
| Server starts, client times out | Firewall, bind address, or long fit | Check the endpoint, firewall, and `journalctl`; increase the client timeout if the fit is slow. |
| `Ice.ConnectionLostException` while sending a full-resolution frame | The raw frame is larger than the server's default 1 MB Ice incoming-message limit | Start the server with `--message-size-max-kb 65536` (the default) or patch older servers to `Ice.initialize(["--Ice.MessageSizeMax=65536"])`, then restart the service. |
| `Ice.ObjectNotExistException` | Wrong identity or proxy | Use `CalibrationPhenoseederIcing` and the printed endpoint. |
| `Proxy does not implement CalibrationPhenoseederIcing` | Contract revision mismatch | Rebuild the client and server from the same `.ice` files and regenerate stubs. |
| Very slow on the Pi | Refit after every observation | Lower `target_observations` for tests; see the optimization recommendations. |

## Security checklist

- [ ] Bind to `127.0.0.1` and use an SSH tunnel, or bind to `0.0.0.0` with a firewall allowlist for known client IPs.
- [ ] Do not expose port 10000 to the Internet.
- [ ] Run the service as a dedicated, least-privilege account.
- [ ] Grant the service account write access only to the archive/procedures root and the local output/debug folders it needs.
- [ ] Protect the service account password and any stored SMB credentials.
- [ ] Keep the OS, Python dependencies, and ZeroC Ice patched.
- [ ] Use read-only Git credentials for automatic updates.
- [ ] Restrict who can push or move release tags; the updater executes code as
      `SYSTEM` or root.
