# Installer artwork

This directory contains the editable Plebian-OS installer mark and the
installer-ready raster exports. The build must consume these tracked files; it
must never read artwork directly from untracked developer files.

See [ATTRIBUTION.md](ATTRIBUTION.md) for upstream credits and the asset-specific
GPL-2.0-or-later terms. The complete license text is included at
[`../COPYING.GPL-2`](../COPYING.GPL-2).

The remaster, bootstrap provisioner, and transactional updater preserve that
relative link by installing the notices at
`/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md` and
`/usr/local/share/doc/plebian-os/COPYING.GPL-2`. Their exact hashes are recorded
in `/etc/plebian-os/build-info.env` for release acceptance.

## Source and runtime map

The mark was promoted from the 2026-07-13 authoring record. From 0.2.4 the
splash and both banners are drawn by [`build/draw-artwork.py`](../../build/draw-artwork.py)
from the mark and the Neuronte large desktop face, and from nothing else:

| Repository file | Source | Runtime use | Required contract | SHA-256 |
|---|---|---|---|---|
| `logo.svg` | `images/logo-geek-angular-p.svg` | Canonical editable angular-P geek mark; not embedded directly by Debian Installer | SVG, 512-square viewBox | `13457ceebdd3bfc498ae41fbc200b37314e8b27d23016912c0811f6594971615` |
| `logo.png` | `images/logo-geek-angular-p.png` | Transparent raster reference/export of `logo.svg` | 1024x1024, 8-bit RGBA PNG, non-interlaced | `e667095e5156417d0c43d2fa60cdf8ec51dba57ea2c54902bfaf4f0e5df13d22` |
| `splash.png` | `build/draw-artwork.py` | Replaces ISO `/isolinux/splash.png`; GRUB and ISOLINUX share it | 640x480, 8-bit RGB PNG, no alpha, non-interlaced | `3e85b926f360e0e3dc33c1c04110ed9a402cd73069c4982a33da535e1851bcc8` |
| `banner.png` | `build/draw-artwork.py` | Overrides GTK initrd `usr/share/graphics/logo_debian.png` | 800x75, 8-bit RGB PNG, no alpha, non-interlaced | `384f10f3c044337f0732acbaca9d0ba907272042389a32833eca19c9f5fd6029` |
| `banner-dark.png` | Byte-for-byte copy of `banner.png` (the drawing is already dark) | Overrides GTK initrd `usr/share/graphics/logo_debian_dark.png` | 800x75, 8-bit RGB PNG, no alpha, non-interlaced | `384f10f3c044337f0732acbaca9d0ba907272042389a32833eca19c9f5fd6029` |

The matching desktop-only treatment is tracked separately as
`../desktop/plebian-os.png`; the same program draws it and it is not embedded
into Debian Installer.

The authoring-source names in the two logo rows document lineage only and are
not build inputs. Those source records are not part of this distribution.

The files these replace in the installer come from this exact Debian image:

```text
debian-13.5.0-amd64-netinst.iso
SHA-256: 95838884f5ea6c82421dfe6baaa5a639dbbe6756c1e380f9fe7a7cb0c1949d2a
rootskel-gtk: 13.0.4
```

Within that ISO, the replaced originals are `/isolinux/splash.png` and the GTK
initrd's `usr/share/graphics/logo_debian.png` and
`usr/share/graphics/logo_debian_dark.png`. Through 0.2.3 the Plebian-OS splash
and banners were edits of those originals; from 0.2.4 they are not, and none
of the originals is an input. [ATTRIBUTION.md](ATTRIBUTION.md) keeps the
upstream notices and the record of the earlier set.

## How the pictures are drawn

```sh
python3 build/draw-artwork.py --neuronte /path/to/neuronte-release          # write the four files
python3 build/draw-artwork.py --neuronte /path/to/neuronte-release --check  # redraw and compare
```

`--neuronte` names a Neuronte release directory holding `build/libneuronte.so`
and `weights/neuronte-ui-large-latin1-v1.nrt`; the program refuses a weight
file whose SHA-256 is not the one it records. It needs Python 3 with NumPy and
Pillow. It uses no random numbers and writes the PNG itself, so the same
inputs give the same bytes; the tracked files were written with zlib 1.3.1,
Pillow 11.1.0 and NumPy 2.2.4. Nothing in a build or an installation runs it:
builds consume the tracked files and check their hashes.

Each picture is a dark vertical gradient, the outline of the mark enlarged and
cropped as a faint background shape, the mark in full colour, and the name
drawn by the Neuronte face in the mark's colour. Positions and sizes are the
three short functions `splash`, `banner` and `wallpaper` in the program.

## Earlier generation chain

This is the record of the mark, which stays, and of the splash and banner
shipped through 0.2.3, which the drawings above replaced. None of these
records is a build input and none is distributed.

| Stage | Authoring record (not distributed) | SHA-256 |
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

The final banner and splash of that chain were normalized to 800x75 and
640x480 with Lanczos filtering; `INSTALLER_IMAGE_REVIEW.md` in the authoring
record has the exact commands.

## No version in artwork

No release number may be baked into any file in this directory. Raster and SVG
artwork contains only the stable `Plebian-OS` identity. BIOS and UEFI menu text
must render the resolved `PLEBIAN_OS_VERSION` at build time.

This policy prevents stale artwork, avoids redrawing and re-pinning images for
a release-only text change, and keeps one asset set reusable across
versions. A release must update bootloader text through the build's authoritative
version path; it must not rename or patch image pixels to carry the version.

## Artwork update workflow

1. **Re-audit the Debian base.** Pin and verify the new ISO SHA-256. Confirm the
   paths and formats of the stock splash and both GTK banners that these files
   replace. Stop if a path or format changed.
2. **Edit the canonical source first.** `logo.svg` is authoritative for the
   angular-P mark, and `build/draw-artwork.py` reads the mark from it. Render
   `logo.png` from it with real transparency; never treat a checkerboard image
   as alpha.
3. **Change the drawing in the program.** Layout, colours and sizes live in
   `build/draw-artwork.py`. Do not edit the PNG files by hand and do not place
   a release version in any bitmap. `banner-dark.png` stays byte-identical to
   `banner.png` unless a separately reviewed treatment is approved.
4. **Redraw and re-pin.** Run the program, then replace the SHA-256 values in
   this README, in `../desktop/README.md`, and wherever the build, the
   provisioner, the updater and the tests name them (search for the old
   value). Update `ATTRIBUTION.md` whenever a source, a copyright, the selected
   license, or the method changes, and re-pin its hash the same way.
5. **Validate before commit.** Run the test suite; `tests/test_artwork_drawing.py`
   redraws the files when `NEURONTE_HOME` names a Neuronte release. Inspect the
   logo at 32 pixels, the banner at its native 75-pixel height, and the splash
   in BIOS and UEFI menu layouts. Confirm the eye, exactly two hair strokes,
   complete orange `>_`, exact `Plebian-OS` spelling, menu contrast, safe
   margins, and absence of any version number.
6. **Test the media result.** Confirm the ISO contains the tracked splash bytes,
   both GTK initrd overrides, branded BIOS/UEFI text in every theme, and a valid
   refresh of every entry in Debian's existing media-check manifest. The
   manifest's upstream entry set excludes `isolinux/` and does not gain newly
   injected files, so verify those payloads separately as described above.
