# Troubleshooting

## Quick reference

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `Config file not found` | Wrong `--config` path | Use an absolute path or the packaged default |
| `Missing config section '[...]'` | Incomplete TOML | Add the missing table/key; see [Configuration](Configuration) |
| `Unknown settings: ...` | Typo in a keyword argument | Check `PossibleOptions` names |
| `robot positions does not match ... images` | CSV names, patterns, or sorting | Verify the CSV fourth column and `image_name_patterns` |
| `At least N valid observations are required` | Too few accepted images | Add images, fix rejections, or lower `n_distortion_coefs` |
| Every image rejected | Direction, background, or sphere detection | Inspect `debug/result####.png`; see below |
| `distortion doesn't show monotonic behaviour` | Unphysical radial model | The fit retries with zero distortion; verify the data |
| Old detections reused | Point cache is enabled | `--no-load-stored-data` |
| Ice server exits immediately | `zeroc-ice` missing | `uv sync --extra ice` |
| Ice client cannot connect | Endpoint, firewall, or identity | Check `Proxy:` output and the port |
| Ice getter raises `RuntimeError` | No fit yet and not ready | Send more images or call `init` correctly |
| Huge one-sigma values | Weakly constrained parameters | More/better distributed data; fix `cx/cy` |
| `NaN` uncertainty | Rank deficiency or no residual degrees of freedom | More observations |

## Input and configuration

### The config file is ignored

Precedence is packaged config → `--config` file → keyword arguments. A value of
`None` does not override anything. Relative paths resolve against the
calibration folder, not the current working directory.

### Robot CSV handling

- The delimiter is `;`.
- The first three fields are `Xr;Yr;Zr`.
- A fourth field is treated as the image name.
- A row whose first field contains `calibration` is skipped.
- Without image names, glob patterns are used and sorted by modification time.

If the counts differ, the loader raises before any analysis.

### Images are not found

Check `image_name_patterns` and `sort_image_names_by_mtime`. If the CSV provides
names, the patterns are ignored and every name is resolved relative to the
calibration folder.

## Image analysis

### Everything is rejected

Start with the debug images:

```text
<folder>/debug/result0000.png
```

Typical causes:

- **Direction is undefined.** The top and bottom bands have similar variation.
  Check that the nozzle is fully visible and that `bg_height_pxs // 2` covers an
  empty band.
- **Sphere is out of FOV.** Increase the margin, move the sphere, or lower
  `min_bg_pixels_on_edges`.
- **Sphere not found.** The background threshold may be wrong. Try
  `fixed_bg_threshold`, a different `bg_color_est_perc`, or a larger
  `bg_height_pxs`.
- **Sigma cannot be estimated.** The edge profile is too noisy or the sphere is
  too small. Increase `blur_est_border_thickness` or improve focus.

### Sphere merges with the nozzle

Decrease `sphere_center_to_nozzle_part` so the circle fit uses less of the
nozzle-side region.

### Radius outliers

The filter flags `|r - mean| > 2.5σ`. Outliers are written as `NaN` in the
cache and are listed in the debug folder when `debug = true`. A few outliers are
normal; many usually indicate a detection or background problem.

## Fitting

### Not enough observations

The minimum is `10 + n_distortion_coefs` (14 with the default `4`). The error
message reports the count after radius filtering. Rejected images never count.

### Distortion fallback

```text
distortion doesn't show monotonic behaviour, and should be neglected
```

The radial model was not positive and monotonic over the image domain, so the
pipeline refit with `n_distortion_coefs = 0`. The YAML result reflects the
fallback. If this happens consistently, reduce the distortion order or improve
the point distribution.

### Fit time

Folder mode refits after every observation (`step_size = 1`). For quick
experiments build a session directly with `fit_every_n=None` and call `finish()`
once, or use a larger `fit_every_n`.

### Weak parameters

Large one-sigma values for `k2`, higher-order terms, or free `cx`/`cy` usually
mean the data does not constrain them. Prefer `fix_cx_cy = true` unless you have
a well-distributed dataset and a specific reason to estimate the principal
point.

### `NaN` uncertainties

`calculate_errors` returns `NaN` when:

- there are no more residuals than parameters;
- the residual or Jacobian values are not finite;
- the pseudoinverse fails.

Add observations or reduce the number of free parameters.

## Cache

If results do not change after editing the analysis settings, the cache is being
reused:

```powershell
3dsc "P:\3Dcalibration\3D_example" --no-load-stored-data
```

The cache stores rejected/outlier rows as `NaN`; a cache copied from another run
can therefore hide changed image names or settings.

## Ice

### The server does not start

```text
ZeroC Ice is not installed. Install the optional extra with:
python -m pip install -e ".[ice]"
```

Install the extra, then re-run `3dsc-ice-server`.

### The client cannot connect

- Confirm the server prints `Ice calibration server listening on ...` and a
  `Proxy:` line.
- Use the same endpoint and identity on both sides.
- For a remote client, bind `tcp -h 0.0.0.0 -p <port>` and open the firewall.
- `connect()` performs a checked cast; a mismatch raises
  `RuntimeError: Proxy does not implement CalibrationPhenoseederIcing`.

### `imageData does not contain any pixel data`

The client sent a struct with an empty pixel vector. Check that the image was
decoded successfully; `add_image_file` raises `could not decode image bytes` for
an unreadable file.

### `imageData.bytePixels has ... values; expected ...`

`height`, `width`, and `spp` do not match the number of pixels. The client fills
these fields automatically, so check for a custom `imageData` producer.

### Wire incompatibility with another client

`CommonPhenoseeder.ice` and `PhytoCommon.ice` are the shared production
definitions, and stub generation also requires the placeholder
`ice/PhytoError.ice`. If another machine uses a different contract revision,
symptoms include unmarshal errors, missing fields, or values that do not match
the production client. See [Ice Interface](Ice-Interface).

### Getter raises “Calibration is not ready and no fitted result is available”

No fit has succeeded yet. Send enough observations to reach
`min_observations`, or call `init` and confirm the procedure/config are correct.

### Procedure and server-config errors

- `missing required setting 'procedures_root'`: add
  `procedures_root = "<absolute path>"` under `[general]` in the `--config` file.
- `'procedures_root' ... must be an absolute path`: use a full Windows drive or
  UNC path, or a full POSIX path.
- A missing `<procedures-root>/<procedure-id>/config.toml` is created from the
  packaged default on the first `init`. If creation fails, make sure the service
  account can write under `<procedures-root>`.
- `configurationfilepath must be an absolute path`: the optional `init` override
  is interpreted on the server, not on the client.
- `procedure 1 has an active calibration`: retrieve the current results first.
  To abandon the session, re-select procedure 1 to reset it, then select the next
  procedure.

## Windows notes

- Quote paths with spaces or commas:
  `"P:\3Dcalibration\3D_20260824_2,3mm"`.
- Use `.\\.venv\\Scripts\\python.exe` when the environment is not activated.
- The debug folder is always created, even when debug images are disabled,
  because failure images are written there.

## Diagnostic checklist

1. Run with `--debug` and read the per-image lines.
2. Inspect `debug/result####.png` for the first rejected image.
3. Check `session.rejections` and `session.last_fit_error` when using the API.
4. Confirm the number of observations after radius filtering.
5. Re-run with `--no-load-stored-data` after changing analysis settings.
6. For Ice, verify the extra, endpoint, identity, and contract version.
