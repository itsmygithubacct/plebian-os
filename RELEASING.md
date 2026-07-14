# Releasing Plebian-OS

Plebian-OS, [pleb](https://github.com/itsmygithubacct/pleb),
[kilix](https://github.com/itsmygithubacct/kilix), and
[kilix-95](https://github.com/itsmygithubacct/kilix-95) are one coordinated
stack. A release uses one version across all four repositories and pins every
network-fetched build input.

The first publishable version is **0.1.1**. The existing `v0.1.0` tags identify
an incomplete candidate and must never be moved or used for a published image.
The current coordinated release is **0.1.2**; its pin manifest was created only
after the four final component commits were known.

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
   firmware before publication. Check the versioned Plebian-OS titles in the
   default, advanced, and accessible-dark menus, then enter the graphical
   installer and verify both banner variants. The angular-P mark must retain
   one eye, two hair strokes, and the complete orange `>_` cursor.
   In an installed guest, complete these distribution-asset checks:

   - verify `/usr/local/share/plebian-os/wallpapers/plebian-os.png` is
     `root:root`, mode `0644`, and has the expected tracked/build-info SHA-256;
   - open **Start > Help > Pleb Recovery Guide**, confirm it displays the
     installed `/usr/local/share/doc/pleb/RECOVERY.md`, and verify the guide
     includes both the full Plebian-OS dependency helper and the
     `libxxhash-dev` fallback;
   - verify a fresh Kilix desktop selects that stable wallpaper path, while an
     existing `.state.json` (including a custom wallpaper choice) remains
     byte-for-byte unchanged across reprovisioning and update;
   - verify firstboot records
     `~/gpu_terminal/{plebian-os,pleb,kilix,kilix-95}` as the coordinated
     source layout and `~/.local/gpu_terminal/` as the data root in build info,
     session defaults, and final provenance; confirm `external`, `builtin`, and
     both `auto` outcomes seed only Pleb's `data/desktop` state, while launching
     Kilix-95 standalone still uses its XP wallpaper;
   - exercise a successful ten-file OS-layer update and an induced failure,
     confirming rollback restores the prior wallpaper, attribution, license,
     scripts, Pleb recovery guide (or removes it if newly created), and state;
     separately test the documented v0.1.1 migration with two updater runs
     (seven-file updater first, ten-file updater second);
   - verify the installed
     `/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md` and
     `/usr/local/share/doc/plebian-os/COPYING.GPL-2` are `root:root`, mode
     `0644`, match their expected hashes, and retain the attribution's working
     relative `../COPYING.GPL-2` reference.
7. Re-check that every local tag resolves to the reviewed commit and that all
   worktrees remain clean. Only then push the four tags and publish the strict
   release artifact, its checksum, and a checksummed release source archive
   containing the exact tracked artwork, editable source, attribution, license
   text, and provenance records used for the image. Publish that source archive
   and provenance alongside the ISO as release assets, rather than relying only
   on a mutable branch checkout. These records support review and redistribution;
   they are evidence of the release inputs, not a legal opinion or guarantee.

If validation fails before publication, fix the problem in new commits and
delete/recreate only the **unpublished local candidate tags**. Once any tag is
published, never move or reuse it; increment the patch version instead.

## Installed version and update semantics

Release images keep exact refs in `/etc/pleb/session.env`. Consequently
`plebian-os-update` verifies and rechecks those same commits; it does not drift
to branch heads. To intentionally move an installed machine to another release,
update all coordinated refs and version together, then run
`plebian-os-update --restart`.
