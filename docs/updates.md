# Updating Plebian-OS

What an update does to an installed system. The operator commands are
summarised in the [README](../README.md#usage); the supported paths and the
release gate are defined in [UPGRADING.md](../UPGRADING.md).

**Updating later** — refresh the whole stack with **`plebian-os-update`**. It
first resolves the highest published stable Plebian-OS release, runs that target
tag's own closure selector, and relaunches the newly installed updater. It then
pulls `~/.local/gpu_terminal/sources/pleb`, re-runs `pleb install`, and delegates
the Kilix, submodule, engine, and optional desktop-provider update to
`pleb update --no-restart`.
It **also refreshes the Plebian-OS layer itself** as one validated, rollback-safe
transaction (provisioner, dependency installer, closure selector, unit, helpers,
version, branded wallpaper, and artwork notices) from a `plebian-os` checkout, so OS-layer fixes reach
installed systems too — pinned
by `PLEBIAN_OS_REF` and disablable with
`PLEBIAN_OS_SELF_UPDATE=0`. The selected `/etc/pleb/closure.env` pins `PLEB_REF`,
`KILIX_REF`, `KILIX95_REF`, and `PLEBIAN_OS_REF`. Those exact refs remain the
authority within the selected release instead of drifting to branch heads. The
target selector validates the complete closure, fetches every exact component
commit, reports each component's ancestry direction, and moves every
release-controlled pin at once while leaving operator choices alone. It also
installs the exact target selector and updater as part of that same recoverable
selection. Use `--revalidate-current` only when you explicitly need to refresh
the already-selected release without hopping. See [UPGRADING.md](../UPGRADING.md)
for the exact contract. Updates are serialized;
participating checkouts with local changes are refused. Before the first change,
the updater snapshots the deployed OS/Pleb files, checkout positions, engine
artifacts, system uv binaries, and final provenance. It reconciles the selected
target dependency policy, including any required uv pin, and rewrites
`packages.list`, `versions.env`, and `apt-sources.list` only after the completed
stack validates. A failure after the OS/dependency refresh, Pleb refresh,
install, component update, or provenance write restores that previous coherent
stack. Apt package additions may remain installed but inactive. Debian package
upgrades are never rolled back. When a machine still uses its install snapshot,
the update moves it to live Debian sources only after the stack has committed.
Fresh 0.2.2 installations already use live sources. The OS-layer stage is also
bound to pre-sudo SHA-256 values and revalidated as root before any destination is
replaced; success is reported only after the entire outer transaction commits.
Pass `--restart` to restart the graphical session after a successful update.
Firstboot and manual reprovisioning hold the same target-user Pleb state lock,
so their checkout, engine, and provider mutations cannot race a direct update.
They also snapshot the provisioner-owned OS/Pleb runtime and configuration
outputs before the first such file is rewritten — branding and notices,
installed helpers and launchers, LightDM and session configuration, sudoers
policy, and final provenance — and commit that filesystem transaction only
after provisioning is complete. A failure or
signal restores the previous files, links, modes, and absences. If an
unexpected path makes automatic restoration unsafe, the command exits 70 and
retains the private `/var/lib/plebian-os/provision-rollback.*` tree for manual
inspection rather than deleting the unexpected data.
Downloaded git objects, package-manager additions, and a newly installed Go
toolchain are intentionally not removed by either rollback; they are additive
and not selected by the restored runtime. Provisioning checkout/build and user
data changes are likewise resumable rather than destructively rewound. During
an update, a checkout created by the failed run is moved into the reported
recovery directory instead of being deleted.

**Upgrade baseline:** install 0.1.7 fresh when moving from any earlier build;
0.1.2 to 0.1.7 is deliberately not an in-place migration. Starting with 0.1.7,
every later release must prove an in-place upgrade from the immediately previous
published release while preserving user data, application state, settings, and
operator choices, with rollback to the prior coherent stack on failure. Direct
skips over a published release require their own explicit acceptance result.
See [UPGRADING.md](../UPGRADING.md) for the machine-readable release policy and
operator contract.
