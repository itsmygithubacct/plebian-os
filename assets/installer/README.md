# Installer artwork

This directory contains the editable Plebian-OS installer mark and the
installer-ready raster exports. The build must consume these tracked files; it
must never read artwork directly from a developer's `~/research` directory.

See [ATTRIBUTION.md](ATTRIBUTION.md) for upstream credits and the asset-specific
GPL-2.0-or-later terms. The complete license text is included at
[`../COPYING.GPL-2`](../COPYING.GPL-2).

The remaster, bootstrap provisioner, and transactional updater preserve that
relative link by installing the notices at
`/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md` and
`/usr/local/share/doc/plebian-os/COPYING.GPL-2`. Their exact hashes are recorded
in `/etc/plebian-os/build-info.env` for release acceptance.

## Source and runtime map

The approved set was promoted from the 2026-07-13 authoring record:

| Repository file | Retained authoring source | Runtime use | Required contract | Approved SHA-256 |
|---|---|---|---|---|
| `logo.svg` | `images/logo-geek-angular-p.svg` | Canonical editable angular-P geek mark; not embedded directly by Debian Installer | SVG, 512-square viewBox | `13457ceebdd3bfc498ae41fbc200b37314e8b27d23016912c0811f6594971615` |
| `logo.png` | `images/logo-geek-angular-p.png` | Transparent raster reference/export of `logo.svg` | 1024x1024, 8-bit RGBA PNG, non-interlaced | `e667095e5156417d0c43d2fa60cdf8ec51dba57ea2c54902bfaf4f0e5df13d22` |
| `splash.png` | `images/installer-splash-geek.png` | Replaces ISO `/isolinux/splash.png`; GRUB and ISOLINUX share it | 640x480, 8-bit RGB PNG, no alpha, non-interlaced | `1110ed74dfc015ff1c5f2420b09428a89d82c278f8a618cf0cc3167b2c0a777c` |
| `banner.png` | `images/installer-banner-geek.png` | Overrides GTK initrd `usr/share/graphics/logo_debian.png` | 800x75, 8-bit RGB PNG, no alpha, non-interlaced | `0317df64efd7af9b03380f301c514357b5a0bd50120abacfd0ebeffb90516772` |
| `banner-dark.png` | Byte-for-byte copy of `banner.png` until a distinct dark treatment is approved | Overrides GTK initrd `usr/share/graphics/logo_debian_dark.png` | 800x75, 8-bit RGB PNG, no alpha, non-interlaced | `0317df64efd7af9b03380f301c514357b5a0bd50120abacfd0ebeffb90516772` |

The matching desktop-only treatment is tracked separately as
`../desktop/plebian-os.png`; it is not embedded into Debian Installer.

The authoring paths in the table are relative to the `research/plebian-os/`
archive on the preparation workstation. They document lineage only and are not
build inputs.

The upstream artwork was anchored to this exact Debian source image:

```text
debian-13.5.0-amd64-netinst.iso
SHA-256: 95838884f5ea6c82421dfe6baaa5a639dbbe6756c1e380f9fe7a7cb0c1949d2a
rootskel-gtk: 13.0.4
```

Within that ISO, the relevant originals are `/isolinux/splash.png` and the GTK
initrd's `usr/share/graphics/logo_debian.png` and
`usr/share/graphics/logo_debian_dark.png`. Source notices were captured at:

```text
research/debian13/images/references/source-metadata/ceratopsian.md
research/debian13/images/references/source-metadata/rootskel-gtk-copyright
```

## Generation chain

The source chain is deliberately separate from the small runtime payload:

| Stage | Record relative to `research/plebian-os/` | SHA-256 |
|---|---|---|
| Initial splash prompt | `prompts/boot-b-terminal-p.prompt.txt` | `e9992f9b956c2cf04a0cdc372e5cadeabfbac1d3eeeb93c6a75ac0212b2be5a1` |
| Initial banner prompt | `prompts/gtk-b-terminal-p.prompt.txt` | `b3d9abab2ab1ee53dbf4ddae5eaada2e748dd2e3967b8c4dbed817cd7888865e` |
| Initial splash model output | `images/generated-raw/boot-b-terminal-p-full.png` | `5f60268aae8da2c49e7e316fd8b415d698d6c008121541e79b193b028f715617` |
| Initial banner model output | `images/generated-raw/gtk-b-terminal-p-full.png` | `b3dd6294d703833b5d7fb919a7bd52a838c2f27356da562b129b2b1fad690396` |
| Selected initial splash | `images/boot-b-terminal-p.png` | `a246ebb38e9a416e221cdeb802e50dd5b711f93dd2af7f276c1760a904db0199` |
| Selected initial banner | `images/gtk-b-terminal-p.png` | `50b9d2173213c3d5f9f6afea7f12c8e8fa4e37c49b87ff3ced3f44da455b8708` |
| Logo-refinement prompt | `prompts/logo-geek-angular-p.prompt.txt` | `148626746c6ddeb618a0f425305d1026b123cded8e82a81605d85cda92a41281` |
| Logo model output | `images/generated-raw/logo-geek-angular-p-concept.png` | `8cd2151f10f1b6e31e452ef51829c74090be3a50b3c34a349769bdc28f5a8873` |
| Final banner prompt | `prompts/banner-geek.prompt.txt` | `5e189d398258af303aefd05f0fce3d8c050221735ff01b2853650412e910ce3f` |
| Final splash prompt | `prompts/installer-splash-geek.prompt.txt` | `655a625410bfd25813d467c765be80e5bbc4acebc96a813c0d78ad8407a2ee6c` |
| Final banner model output | `images/generated-raw/installer-banner-geek-full.png` | `e04ccf660c69f7fb657c75b489c79be74a5ad23775d6332643e33db96590abc4` |
| Final splash model output | `images/generated-raw/installer-splash-geek-full.png` | `d34d6d96a545a446398dd89594a228a4afde3a48dd26dcb04bc5de6982f95add` |

`INSTALLER_IMAGE_REVIEW.md` records the exact final normalization commands. In
summary, the banner retains the top 192 pixels of the trimmed 2048-pixel-wide
generated strip, then is resized to exactly 800x75. The splash is resized to
exactly 640x480. Both use Lanczos filtering, metadata stripping, 8-bit depth,
and a forced PNG24 output.

## No version in artwork

No release number may be baked into any file in this directory. Raster and SVG
artwork contains only the stable `Plebian-OS` identity. BIOS and UEFI menu text
must render the resolved `PLEBIAN_OS_VERSION` at build time.

This policy prevents stale artwork, avoids regenerating lossy/model-assisted
images for a release-only text change, and keeps one asset set reusable across
versions. A release must update bootloader text through the build's authoritative
version path; it must not rename or patch image pixels to carry the version.

## Artwork update workflow

1. **Re-audit the Debian base.** Pin and verify the new ISO SHA-256. Extract the
   stock splash, both GTK banners, package version, and current source copyright
   metadata. Stop if paths, formats, authorship, or license terms changed.
2. **Work outside the build tree.** Retain exact prompts, supplied references,
   full model outputs, and selected candidates in a dated research record. Note
   the generation provider, model/version, date, seed when available, tool
   versions, and every deterministic conversion command.
3. **Edit the canonical source first.** `logo.svg` is authoritative for the
   angular-P mark. Render `logo.png` from it with real transparency; never treat
   a checkerboard image as alpha.
4. **Normalize runtime files.** Export the splash and both banners to their
   exact dimensions and PNG color contracts. Do not place a release version in
   any bitmap. Keep `banner-dark.png` byte-identical to `banner.png` unless a
   separately reviewed accessible-dark treatment is approved.
5. **Promote stable names.** Copy only the canonical vector, its transparent
   raster reference, and the three normalized runtime files into this directory.
   Builds must not depend on raw generations or workstation-local paths.
6. **Update the record.** Replace the source/runtime hashes and generation-chain
   hashes in this README. Update `ATTRIBUTION.md` whenever the upstream source,
   copyright, selected license, or editing method changes.
7. **Validate before commit.** Verify all SHA-256 values; parse PNG IHDR fields
   for dimensions, 8-bit depth, RGB/RGBA type, and non-interlacing; compare the
   two banners when they are meant to match. Inspect the logo at 32 pixels, the
   banner at its native 75-pixel height, and the splash in BIOS and UEFI menu
   layouts. Confirm the eye, exactly two hair strokes, complete orange `>_`,
   exact `Plebian-OS` spelling, menu contrast, safe margins, and absence of any
   version number.
8. **Test the media result.** Confirm the ISO contains the tracked splash bytes,
   both GTK initrd overrides, branded BIOS/UEFI text in every theme, and a valid
   refresh of every entry in Debian's existing media-check manifest. The
   manifest's upstream entry set excludes `isolinux/` and does not gain newly
   injected files, so verify those payloads separately as described above.
