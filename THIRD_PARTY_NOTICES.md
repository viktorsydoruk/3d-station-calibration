# Third-party notices

This project is licensed under the Apache License 2.0. See `LICENSE`.

The table below summarizes the direct dependencies declared in `pyproject.toml`.
It is an informational audit, not legal advice. Transitive dependencies and
binary-wheel contents should be checked again before a release.

| Package | Declared role | License | Compatibility notes |
|---|---|---|---|
| NumPy | runtime | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Permissive; compatible with Apache-2.0 distribution when notices are retained. |
| SciPy | runtime | BSD-3-Clause | Permissive. Binary wheels can bundle OpenBLAS/LAPACK (BSD-3-Clause) and GCC runtime files under GPL-3.0-or-later WITH GCC-exception-3.1. |
| opencv-python | runtime | Apache-2.0 | Same license family as this project. |
| Matplotlib | runtime | Matplotlib/PSF-style license | Permissive; retain the Matplotlib license notice when redistributing. |
| PyYAML | runtime | MIT | Permissive. |
| ipykernel | optional `notebooks` extra | BSD-3-Clause | Permissive. |
| pytest | development | MIT | Permissive. |
| scipy-stubs | development | BSD-3-Clause | Permissive. |
| ZeroC Ice (`zeroc-ice`) | optional `ice` extra | GPL-2.0-only, with ZeroC's additional exception | See the warning below. |

## ZeroC Ice

ZeroC Ice is **not** a permissive dependency. Its package metadata declares
`GPL-2.0-only`, and ZeroC's `ICE_LICENSE` adds an exception that explicitly
permits combining Ice with software licensed under Apache-2.0.

The practical consequences are:

- The core calibration package can remain Apache-2.0 because it works without
  Ice (for example, the folder workflow).
- Ice is therefore kept in an optional extra:
  ```powershell
  python -m pip install -e ".[ice]"
  ```
- Do not vendor Ice into the Apache-2.0 wheel.
- Distributing a bundle, executable, or container that contains Ice still
  triggers GPLv2 obligations for Ice and for the combined distribution. Include
  the GPLv2 text and the corresponding source/notice information for Ice, and
  review the distribution model with your institution's legal contact.

ZeroC's license and exception:
<https://github.com/zeroc-ice/ice/blob/3.8/ICE_LICENSE>

## Apache-2.0 compatibility summary

Apache-2.0 is compatible with the permissive BSD, MIT, Zlib, PSF-style, and
Apache-2.0 dependencies above. GPL-2.0-only is generally incompatible with
Apache-2.0, but ZeroC's explicit exception covers combining Ice with
Apache-2.0 software. That exception does not remove the GPLv2 obligations that
apply when Ice itself is distributed.
