# Ice interface

The Ice contract is not wired into the package yet. The current interface file
remains at:

```text
_3dsc_resources/CalibrationPhenoseederIcing.ice
```

It is intentionally untouched until the shared `CommonPhenoseeder.ice` and
`PhytoCommon.ice` files are available for `slice2py`.

When the contract is ready, put the `.ice` source in this folder and generate
Python stubs into:

```text
src/station_calibration/ice/generated/
```

Hand-written transport code belongs in `src/station_calibration/ice/`:

```text
adapter.py   Ice types <-> station_calibration domain models
server.py    Ice servant and session registry
client.py    convenience client
```
