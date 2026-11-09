# Requirements and configuration

The short list is in the [README](../README.md#requirements). This page keeps
the full requirements and the configuration files and variables that select a
desktop, a release closure and build inputs.

## Requirements

- An AMD64 machine for the currently selected 0.2.2 binary closure. ARM64
  development builds require their own matching artifacts and qualification.
- A GPU with a KMS/DRM driver for hardware GL, or llvmpipe software GL as a
  fallback (kilix is a GPU terminal). No graphics at all → the greeter still
  works; the Pleb session falls back to a screen-filled kilix or a plain xterm.
- Network on first boot (it clones from GitHub).
- Go ≥ 1.26 for the Kilix fork build. Firstboot installs or upgrades the exact
  pinned Go archive through pleb's checksum-verifying, rollback-safe helper when
  the target does not already have a suitable toolchain.
  `PLEBIAN_OS_KILIX_GO_VERSION` plus the architecture-specific
  `PLEBIAN_OS_KILIX_GO_SHA256_AMD64` / `_ARM64` pins make that toolchain exact
  and integrity-checked. Exact installs must also carry Pleb's root-owned
  `.pleb-source` archive stamp; a same-version binary without the matching stamp
  is reinstalled. Release-controlled pins persist into `/etc/pleb/closure.env`;
  operator choices remain in `/etc/pleb/session.env`.
- 4 GiB RAM is the release-tested installation baseline because the fork build
  compiles large generated Go packages during firstboot. Lower-memory runtime
  use remains possible after installation, but builders warn below 4 GiB.

Release-controlled source and artifact pins live in `/etc/pleb/closure.env`.
The selector migrates older mixed files and updates those pins transactionally;
do not edit them by hand. `/etc/pleb/session.env` retains operator choices,
comments and unknown keys. Session desktop/kiosk policy is also recorded in
`/etc/default/plebian-os`; selecting a release preserves installed choices.
See [UPGRADING.md](../UPGRADING.md) for precedence and migration details. Fresh images
default to `PLEBIAN_OS_DESKTOP=1` and `PLEBIAN_OS_KIOSK=0`: LightDM logs into
the main screen-filling Kilix instance with its chrome visible and the external
Kilix-95 provider already running as page 1. Exiting Kilix returns to the greeter
instead of respawning it. `KILIX_DESKTOP_FLAVOR=95` makes the release appearance
explicitly 95 rather than XP. Setting `PLEBIAN_OS_DESKTOP=0` is the opt-in shell
mode; it starts a bare shell in page 1, from which `kilix desktop` can still open
the selected provider in another Kilix page. In desktop mode,
`KILIX_DESKTOP_PROVIDER` can be
`auto`, `builtin`, `external`, `xp`, `cap`, `tui`, `land`, `command`, or
`none`; `cap` downloads and locally builds Kilix Cap, `tui` installs the Kilix
TUI desktop from the pinned `kilix-tui-utils` checkout, and `land` downloads
and builds Kilix Land with its recursive dependencies. `command` uses
`KILIX_DESKTOP_COMMAND` for other desktops. `KILIX_DESKTOP_FLAVOR=95|xp`
selects the first-launch Kilix 95 flavor, and `none` behaves like a plain shell
session. Kilix Cap uses `KILIX_CAP_*`, Kilix TUI uses
`KILIX_TUI_UTILS_*`, Kilix Land uses `KILIX_LAND_DESKTOP_*`, and external
Kilix 95 uses `KILIX95_*`. The Cap, TUI, and Land source commits are inherited
through the pinned Kilix commit rather than receiving independent
coordinated-release keys. Set
`PLEBIAN_OS_BUILD_KILIX_FORK=0` only when
you deliberately want to allow the prebuilt fallback engine. Release-style
images can set `PLEBIAN_OS_RELEASE_MODE=1`, `PLEBIAN_OS_NETINST_URL`,
`PLEBIAN_OS_NETINST_SHA256`, `PLEBIAN_OS_APT_SNAPSHOT`, `PLEB_REF`, `KILIX_REF`,
`KILIX95_REF`, `KILIX_PREBUILT_VERSION`, `KILIX_PREBUILT_SHA256`, and the exact
Go version/architecture checksums before building. Simpler: set
`PLEBIAN_OS_RELEASE=0.2.2` from a checkout of the `v0.2.2` tag to load its
[`releases/0.2.2.env`](https://github.com/itsmygithubacct/plebian-os/blob/v0.2.2/releases/0.2.2.env)
(see [RELEASING.md](../RELEASING.md)). This selects build inputs; on an installed
system use the coordinated updater or `plebian-os-select-closure 0.2.2`
followed by `plebian-os-update`. The release manifest leaves
`PLEBIAN_OS_APT_SNAPSHOT` empty:
apt tracks the signed live Debian `trixie`, `trixie-updates`, and
`trixie-security` suites with replay protection enabled, and
`unattended-upgrades` applies Debian security updates daily without rebooting.
On historical snapshot-based installs, the installer's `sources.list` is
retired to `/etc/apt/sources.list.plebian-os-installer-snapshot` (a file you want kept
as your own can carry the line `# plebian-os: keep`; see
[UPGRADING.md](../UPGRADING.md#debian-security-updates)); sources Plebian-OS
disabled for the install are restored, and operator sources that already
provide live Debian are used as they are.
Enabled release-mode `uv` installs require exact version/checksum pins and are
verified after installation. The 0.1.9 policy requires `uv` 0.12.3 and rejects
a final manifest that disables it or changes its verified installer checksum.
Installed package/source/tool manifests make the resolved result auditable.
