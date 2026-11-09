# Layout

| Path | What |
|---|---|
| `provision/plebian-os-provision.sh` | the provisioner: apt deps → clone pleb → `pleb install` → set the session |
| `provision/plebian-os-firstboot.service` | systemd oneshot that runs it once on first boot |
| `provision/lightdm-gtk-greeter.conf` | fixed greeter override selecting the installed Plebian wallpaper |
| `provision/plebian-os-nvidia-driver` | optional NVIDIA driver installer; put on `PATH`, never run automatically ([below](nvidia-driver.md)) |
| `preseed/preseed.cfg` | a regular Debian install, no desktop task, wires in the provisioner |
| `build/remaster-iso.sh` | inject the preseed + provisioner into a trixie netinst ISO |
| `build/brand-installer.py` | validate artwork, brand BIOS/UEFI text, and refresh Debian's existing media-check entries |
| `assets/installer/` | editable logo, installer-ready artwork, provenance, and licensing |
| `assets/desktop/` | matching desktop wallpaper, installed at `/usr/local/share/plebian-os/wallpapers/plebian-os.png` |
| `build/make-usb.sh` | build the ISO and flash it to a USB stick (with safety guards) |
| `build/acceptance-vm.sh` | automated VirtualBox release gate: clean candidate binding, instrumented install, lifecycle checks, checksummed report |
| `build/acceptance-release-iso.sh` | validate the exact strict ISO closure and prepare operator-driven BIOS and EFI installs |
| `build/install-vm-from-usb-iso.sh` | build a USB-style ISO, then install it in a 4 GB / 4-core VirtualBox VM |
| `bootstrap.sh` | run the provisioner on an already-installed Debian |
| `VERSION` / `releases/*.env` | shared release version + coordinated pin manifests |
| `RELEASING.md` | how to cut a coordinated pleb/kilix/kilix-95/plebian-os release |
| `UPGRADING.md` / `releases/upgrade-policy.json` | supported upgrade paths, preservation and rollback gate |

Every remastered ISO also stages `/etc/plebian-os/build-info.env` and
`/etc/default/plebian-os` into the installed system. The manifest records the
Plebian-OS commit/dirty state, source Debian ISO checksum, installer and desktop
artwork checksums, voice source/library/model URLs and checksums, and the
repo/ref/provider knobs used for that image; the firstboot env is what
`plebian-os-firstboot.service` reads when it provisions the installed system.
After provisioning finishes, `/var/lib/plebian-os/packages.list`,
`versions.env`, and `apt-sources.list` record the final installed packages,
resolved source commits, tool/engine versions, and apt indexes actually used.
For 0.2.2, `apt-sources.list` records the live Debian indexes used during
installation and subsequent updates or re-provisioning. Historical images
with a timestamped install policy record snapshot indexes until the machine
migrates to live sources, then record the live indexes they resolved against.
