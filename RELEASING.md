# Releasing Plebian-OS

Plebian-OS, [pleb](https://github.com/itsmygithubacct/pleb),
[kilix](https://github.com/itsmygithubacct/kilix), and
[kilix-95](https://github.com/itsmygithubacct/kilix-95) are one coordinated
stack. A release uses one version across all four repositories and pins every
network-fetched build input.

The first publishable version is **0.1.1**. The existing `v0.1.0` tags identify
an incomplete candidate and must never be moved or used for a published image.

## Version commands

| Component | Command |
|---|---|
| Plebian-OS | `plebian-os-update --version`, `plebian-os-provision --version` |
| pleb | `pleb --version` |
| kilix | `kilix --kilix-version` (`kilix --version` reports its engine) |
| kilix-95 | `python3 main.py --version` |

## Release closure

`releases/<x.y.z>.env` must include:

- the coordinated source refs for all four repositories;
- a stable Debian archive URL and SHA-256 for the source netinst;
- a `snapshot.debian.org` timestamp covering installer and firstboot packages;
- the fallback kitty bundle version and SHA-256;
- the exact Go version and SHA-256 for every supported build architecture;
- pinned installer versions/checksums for any optional network installers that
  are enabled (currently `uv`).

Release mode fails closed when a required value is empty, still a placeholder,
malformed, dirty, or does not resolve to the checked-out Plebian-OS commit. The
image records the transformed preseed, source ISO, refs, runtime configuration,
and tool pins in `/etc/plebian-os/build-info.env`; final package and resolved
source/tool manifests are written under `/var/lib/plebian-os/`.

## Cutting `<x.y.z>`

1. Update `VERSION` and `CHANGELOG.md` in all four repositories. Create and
   review `releases/<x.y.z>.env`; verify every URL and checksum from its official
   upstream source.
2. Run each repository's complete test/lint suite and integration contract
   tests. Confirm all four worktrees are clean, review their exact commits, and
   commit the coordinated changes.
3. Push the reviewed commits **without tags**. Firstboot fetches the exact
   component SHAs from GitHub, so the pinned acceptance guest cannot test an
   unpublished object. A failed acceptance is fixed with new commits; no
   immutable release ref has been published at this point.
4. Create **local, annotated** `v<x.y.z>` candidate tags on the reviewed
   commits. Do not push the tags yet. This lets `PLEBIAN_OS_REF=v<x.y.z>` resolve
   while the strict release-image checkout guard is active.
5. Build the pinned artifact from the tagged Plebian-OS checkout:

   ```sh
   PLEBIAN_OS_RELEASE=<x.y.z> build/remaster-iso.sh '' \
       "plebian-os-<x.y.z>-amd64.iso"
   sha256sum "plebian-os-<x.y.z>-amd64.iso"
   ```

6. Run the operator acceptance install (`build/acceptance-vm.sh --replace`). It
   creates a clearly non-publishable SSH/autoboot derivative while loading the
   exact release-manifest source, media, snapshot, toolchain, and provider pins.
   Verify firstboot, provider, update/status, provenance, kiosk-off/on, and
   restart paths. Also boot the strict release artifact on both BIOS and UEFI
   firmware before publication.
7. Re-check that every local tag resolves to the reviewed commit and that all
   worktrees remain clean. Only then push the four tags and publish the strict
   release artifact plus its checksum.

If validation fails before publication, fix the problem in new commits and
delete/recreate only the **unpublished local candidate tags**. Once any tag is
published, never move or reuse it; increment the patch version instead.

## Installed version and update semantics

Release images keep exact refs in `/etc/pleb/session.env`. Consequently
`plebian-os-update` verifies and rechecks those same commits; it does not drift
to branch heads. To intentionally move an installed machine to another release,
update all coordinated refs and version together, then run
`plebian-os-update --restart`.
