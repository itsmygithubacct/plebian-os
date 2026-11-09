# Optional NVIDIA driver

Plebian-OS ships the open-source **nouveau** driver, which drives a display on
any supported NVIDIA card, needs no out-of-tree kernel module, and never breaks
on a kernel upgrade. For most machines that is the right answer and there is
nothing to do.

What nouveau cannot provide is CUDA (it exposes no compute API at all),
NVENC/NVDEC hardware video encode and decode, and full memory/core clocks on
recent silicon — its reclocking is limited or absent there, so the card runs
well below its rated speed.

Machines that need any of those can install NVIDIA's proprietary driver with:

```sh
plebian-os-nvidia-driver --check      # read-only preflight; no root needed
sudo plebian-os-nvidia-driver --install
sudo reboot
plebian-os-nvidia-driver --status     # verify; also try nvidia-smi
```

`sudo plebian-os-nvidia-driver --rollback` purges the driver and returns the
machine to nouveau.

This is **entirely optional**. The provisioner puts the helper on `PATH` so it
is discoverable, and never runs it — nothing in the image depends on it, and no
NVIDIA package is installed by default.

It installs the Debian way: the driver comes from Debian's `non-free`
component as a `.deb`, `nvidia-detect` chooses the package by PCI ID, the
kernel module is built by DKMS so it rebuilds itself on future kernel upgrades,
and nouveau is blacklisted by the driver package's own maintainer scripts. It
never fetches the `.run` installer from nvidia.com, which installs outside dpkg
and silently breaks on the next kernel update.

**It refuses when the hardware is too old.** NVIDIA drops older GPU families
from each driver branch, and Debian retires the matching legacy packages as
they go unmaintained upstream. If `nvidia-detect` steers the card to a legacy
series that is no longer in the archive — or reports it as unsupported
outright — the helper stops before installing anything and says so. Installing
the current driver on such a card produces a machine whose X server will not
start after the reboot; staying on nouveau is the correct outcome, and the
helper leaves it there.

On hybrid-graphics laptops the integrated GPU keeps driving the display, which
is expected. Run individual programs on the NVIDIA GPU with PRIME render
offload:

```sh
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia <program>
```

CUDA needs none of that — it addresses the device directly.
