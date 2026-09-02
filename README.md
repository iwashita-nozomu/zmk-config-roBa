# zmk-config-roBa

<img src="keymap-drawer/roBa.svg">

## Pinned build environment

Firmware and keymap drawings are generated through the repository-owned Issue #164 entrypoint. The host only needs Docker; ZMK, west, Zephyr SDK, and keymap-drawer are installed or executed inside the pinned OCI environment.

```sh
./scripts/zmk-env verify  # validate all checked-in locks
./scripts/zmk-env build   # build firmware once
./scripts/zmk-env repeat  # build twice and require identical identities
./scripts/zmk-env draw    # regenerate keymap-drawer/roBa.{yaml,svg}
```

`toolchain/versions.env` is the authoritative environment lock. `config/west.yml` pins the root ZMK and PMW3610 revisions, the entrypoint rejects an unexpected resolved Zephyr revision, and each run writes the full frozen west manifest plus source, image, toolchain, input, and artifact SHA-256 evidence under `artifacts/`.

The firmware build matrix and keyboard behavior remain owned by `build.yaml`, `config/`, `boards/`, and the upstream ZMK sources; this environment only makes those existing inputs reproducible.
