# Releasing Plebian-OS

Plebian-OS, [pleb](https://github.com/itsmygithubacct/pleb),
[kilix](https://github.com/itsmygithubacct/kilix), and
[kilix-95](https://github.com/itsmygithubacct/kilix-95) ship as **one
coordinated release sharing a single version number**. This is how a release is
cut.

## Version scheme

All four repos carry a `VERSION` file holding the same `MAJOR.MINOR.PATCH`. The
current series is **0.1.0**. Plebian-OS records the version it was built with
into every image — `/etc/plebian-os/build-info.env` and `/etc/pleb/session.env`
both carry `PLEBIAN_OS_VERSION` — and each component reports it:

| Component | Command |
|---|---|
| Plebian-OS | `plebian-os-update --version`, `plebian-os-provision --version` |
| pleb | `pleb --version` |
| kilix | `kilix --kilix-version` (the plain `kilix --version` reports the *engine*) |
| kilix-95 | `python3 main.py --version` |

## Cutting `<x.y.z>`

1. Bump `VERSION` to `<x.y.z>` in **all four** repos and update `CHANGELOG.md`.
2. Tag each repo `v<x.y.z>` on the reviewed commit and push the tags.
3. Pick the exact Debian netinst to pin and record its checksum:
   `sha256sum <debian-…-netinst.iso>`.
4. Pick the prebuilt kitty engine version + its `.txz` sha256 (the fork-build
   fallback).
5. Copy `releases/0.1.0.env` to `releases/<x.y.z>.env` and fill every
   `REPLACE_ME`: `KILIX_PREBUILT_VERSION`, `KILIX_PREBUILT_SHA256`, and
   `PLEBIAN_OS_NETINST_SHA256`. Optionally pin `PLEBIAN_OS_APT_SNAPSHOT` to a
   [snapshot.debian.org](https://snapshot.debian.org) timestamp for a fully
   reproducible apt closure at first boot.
6. Build the release image:
   ```sh
   PLEBIAN_OS_RELEASE=<x.y.z> build/remaster-iso.sh
   ```
   Release mode refuses to build until every pin is present and non-placeholder,
   and fails closed if any checksum does not match.
7. Verify the image end-to-end (`build/acceptance-vm.sh`) and publish.

The `v<x.y.z>` tags are what `releases/<x.y.z>.env` pins `PLEB_REF` /
`KILIX_REF` / `KILIX95_REF` / `PLEBIAN_OS_REF` to, so a release image tracks the
exact tagged commit of every component — and `plebian-os-update` on that image
keeps using those pins instead of drifting to branch heads.
