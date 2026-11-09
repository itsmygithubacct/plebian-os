# Plebian-OS

<p align="center">
  <img src="assets/installer/logo.png" width="160" alt="Plebian-OS angular-P geek logo">
</p>

Plebian-OS is a Debian 13 (trixie) install whose graphical session is
[Pleb](https://github.com/itsmygithubacct/pleb#readme) running one
screen-filling [Kilix](https://github.com/itsmygithubacct/kilix#readme), with the
[Kilix 95](https://github.com/itsmygithubacct/kilix-95#readme) desktop as its
first page, in place of a conventional desktop environment.

**Status:** 0.2.2 is the latest published release (November 3, 2026), an AMD64
installer ISO on the [Releases page](https://github.com/itsmygithubacct/plebian-os/releases).
0.2.3 is in release-candidate testing: the current candidate is the
`v0.2.3-rc6` tag, and its image, update and release acceptance are still open
(see the [0.2.3 notes](releases/0.2.3-notes.md)). This repository is the
release root: its installer recipe, first-boot provisioner, updater and
`releases/<version>.env` manifests decide which commit of every other
repository a Plebian-OS user receives.

## What it does

- Installs stock Debian 13 with no desktop-environment task, plus Xorg,
  LightDM and a thin graphical base.
- On first boot, provisions the Pleb session from the exact source and artifact
  pins of one release manifest: Pleb, Kilix, Kilix 95, and the desktop, media,
  voice, licence and model components they select.
- Logs you in to one screen-filling Kilix with its page strip and pane controls
  visible, Kilix 95 running as page 1. Graphical programs open inside Kilix
  tabs through `kilix run`; a bare Openbox underneath handles unavoidable
  native windows.
- Updates the whole stack as one validated transaction that rolls back to the
  previous coherent stack on failure, one published release at a time.
- Otherwise stays Debian: apt, daily Debian security updates through
  `unattended-upgrades`, a text console on `Ctrl+Alt+F2`, and the open nouveau
  driver with an optional NVIDIA helper.

## Get it

| | |
|---|---|
| Latest release | Plebian-OS 0.2.2 for Debian 13, AMD64: [installer ISO (964 MiB)](https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/plebian-os-0.2.2-amd64.iso), [SHA256SUMS](https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/SHA256SUMS), [release notes and known issues](https://github.com/itsmygithubacct/plebian-os/releases/tag/v0.2.2) |
| Release candidate | 0.2.3, tag [`v0.2.3-rc6`](https://github.com/itsmygithubacct/plebian-os/tree/v0.2.3-rc6): [notes](releases/0.2.3-notes.md), [follow-ups](releases/0.2.3-followups.md); no release ISO is published |
| Reproducing a release | the immutable `vX.Y.Z` tag and its `releases/X.Y.Z.env` manifest ([RELEASING.md](RELEASING.md)) |

The 0.2.2 qualification covers QEMU/KVM BIOS and EFI virtual machines.
Bare-metal USB installation and physical GPU operation were not qualified.
ARM64 is not a supported OS release target, and Windows is a separate preview
(`windows-v0.2.2-preview.4`).

## Quick start

### Install from the ISO

Download the ISO and `SHA256SUMS` into one directory and check the image:

```sh
sha256sum --check --ignore-missing SHA256SUMS
```

Boot it in a virtual machine, or write it to a USB stick with
`build/build_usb_image.py` from a checkout of this repository, which refuses
system disks and asks you to retype the device path:

```sh
build/build_usb_image.py --iso plebian-os-0.2.2-amd64.iso --device /dev/sdX
```

Install it like normal Debian. The installer asks for the hostname,
your full name, a username and a password; root login stays disabled and no SSH
server is installed. The machine needs a network connection on first boot:
`plebian-os-firstboot.service` provisions the stack before the greeter starts,
then LightDM offers the **Pleb** session.

### Convert an existing Debian 13

[`bootstrap.sh`](bootstrap.sh) runs the same provisioner on an installed Debian.
For 0.2.2, first download the release asset
[`ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz`](https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz)
and check it against the same `SHA256SUMS`; the bootstrap never downloads it.

```sh
mkdir -p ~/.local/gpu_terminal/sources
git clone --branch v0.2.2 https://github.com/itsmygithubacct/plebian-os ~/.local/gpu_terminal/sources/plebian-os
carrier="$HOME/Downloads/ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz"
~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh --ollama-carrier "$carrier" --dry-run
sudo ~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh --ollama-carrier "$carrier"
```

Add `--kiosk` to boot straight into Pleb with autologin. Log out and choose
**Pleb** at the greeter.

### Build the installer ISO

`build/remaster-iso.sh` downloads and verifies the Debian netinst itself. The
large release inputs are always supplied as local files and checked against
their pins: the Ollama carrier (above), and from 0.2.3 the default model
archive and the Ask command model archive pinned in
[`provision/default-models.json`](provision/default-models.json) and
[`provision/command-model.json`](provision/command-model.json).

```sh
export PLEBIAN_OS_OLLAMA_CARRIER=/path/to/ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz
export PLEBIAN_OS_DEFAULT_MODELS_BUNDLE=/path/to/default-models-0221.tar.xz
export PLEBIAN_OS_COMMAND_MODEL_BUNDLE=/path/to/lfm2-kilix-commands-20261106-v9.tar.gz
build/remaster-iso.sh                       # writes the installer ISO
build/make-usb.sh --list                    # find the USB stick
build/build_usb_image.py --device /dev/sdX  # build and flash it, with device safety checks
```

Publishable media follow [RELEASING.md](RELEASING.md). Automated VM images are a
separate profile under `~/.local/gpu_terminal/plebian-os/artifacts/acceptance/`:
they erase their target disk, carry the volume label `PLEBIAN-TEST-ERASES-DISK`,
and must never be written to USB or booted on real hardware. See
[docs/installation.md](docs/installation.md),
[build/build_usb_image.md](build/build_usb_image.md) and
[build/build_vm_image.md](build/build_vm_image.md).

## Usage

| Command | What it does |
|---|---|
| `pleb update --to X.Y.Z --dry-run` | Validate the next published release and report every component move; changes nothing. |
| `pleb update --to X.Y.Z` | Apply that one release hop as a single transaction. |
| `pleb update --latest` | Move to the newest release, refusing when that would skip a published one. |
| `pleb update --show` / `--rollback` | Show each selected release value and its source file / restore the previous closure and stack. |
| `plebian-os-update [--restart]` | Select the highest published stable release and refresh the whole stack; the hops above run it to apply their selection. |
| `kilix-settings` (or `pleb settings`) | Top-bar items, pane-title buttons, thermal status and session logging. |
| `kilix transcript` | List and print the per-pane session logs (on by default). |
| `kilix pty` | PTY Sessions: attach to, refresh or end persistent panes. |
| `tmux-tui`, `tb` | Tmux Manager and the tmux-cli command. |
| `ask "..."` | 0.2.3: alias for `kilix ask`, which turns a plain request into a checked Kilix action. |
| `kilix help-setup`, `kilix help-answer "..."` | 0.2.3: download the local Help model once, then ask how to use Kilix and Plebian-OS. |
| `plebian-os-nvidia-driver --check` | Read-only preflight for the optional NVIDIA driver ([docs/nvidia-driver.md](docs/nvidia-driver.md)). |
| `Ctrl+Alt+F2` | A plain text console. |

## How it works

```
 build/remaster-iso.sh: Debian 13 netinst + preseed + provisioner + pinned carriers
        │
        ▼
 Debian Installer        no desktop task; identity asked interactively;
        │                late_command installs the provisioner and first-boot unit
        ▼
 first boot              plebian-os-provision.sh: apt dependencies, clone
        │                plebian-os and pleb, `pleb install` (Kilix, Kilix 95,
        │                fork engine, pinned runtimes), register the Pleb session
        ▼
 every boot              LightDM ─▶ pleb-session ─▶ Kilix (page 1: Kilix 95)
```

**Install.** The ISO is a stock Debian netinst remastered by
[`build/remaster-iso.sh`](build/remaster-iso.sh). The
[preseed](preseed/preseed.cfg) selects no desktop task, leaves identity and
partitioning to Debian Installer, and its `late_command` installs the
provisioner, the first-boot unit and the release environment
(`/etc/default/plebian-os`, `/etc/plebian-os/build-info.env`). The remaster
brands the boot menus and installer from [`assets/installer/`](assets/installer/)
and also generates the ISO's own `README.txt` and `README.html`.

**First boot.** `plebian-os-firstboot.service` runs
[`provision/plebian-os-provision.sh`](provision/plebian-os-provision.sh) once
after the network is up, with a bounded number of attempts (three by default).
It installs the Debian dependencies, clones `plebian-os` and `pleb` into
`~/.local/gpu_terminal/sources/`, and runs a managed `pleb install`, which
clones Kilix and Kilix 95, builds the Kilix fork engine with a pinned Go
toolchain, and registers **Pleb** as a LightDM session. Every ref comes from
the release manifest, so the installed stack is the one that release was
accepted with. The full step list is in
[docs/installation.md](docs/installation.md), and
`journalctl -u plebian-os-firstboot.service` shows a run.

**Updates.** Release-controlled pins live in `/etc/pleb/closure.env` and
operator choices in `/etc/pleb/session.env`. A release hop runs the closure
selector extracted from the target's own published tag, checks that every
component commit is published, moves all pins together, and then lets
`plebian-os-update` refresh the OS layer, Pleb, Kilix and the providers as one
recoverable transaction. Upgrades go one published release at a time from the
0.1.7 baseline. See [docs/updates.md](docs/updates.md) and the contract in
[UPGRADING.md](UPGRADING.md).

Plebian-OS is a thin layer: it decides which repositories to pull and at which
commit, and Pleb turns Kilix into the session. Nothing here forks or vendors
Kilix or Pleb.

## What ships

The 0.2.3 candidate selects, through [`releases/0.2.3.env`](releases/0.2.3.env):

- **Session and desktop:** Pleb, Kilix (with its kitty fork engine and a
  pinned prebuilt kitty 0.48.2 fallback), and the external Kilix 95 provider in
  its 95 flavor (XP is its other flavor). Kilix Cap, Kilix TUI and Kilix Land
  are optional providers pinned through Kilix; Kilix IceWM provides a
  conventional window manager inside Kilix's private X session.
- **Pinned components:** kilix-system-monitor, kilix-desktop-sdk, kilix-icewm,
  kilix-media-sdk, kilix-waydroid (Android stays a first-use install),
  kilix-secrets, kilix-voice (read-aloud and offline dictation), kilix-license,
  the kilix-mpv terminal player package, the libkilix-encodec native package
  and a Qt runtime bundle.
- **Installed by `pleb install`:** the Kilix persistent PTY broker,
  kilix-tui-utils (Kilix TUI desktop, Temps, Memory, Music), tmux-tui and
  tmux-cli, Kilix Voice, and the pinned Media Player (kilix-amp) and PDF Viewer
  (kilix-pdf). Provisioning also installs the catalog-pinned kilix-needle
  application with `kilix app install kilix-needle`.
- **Local inference:** the Ollama 0.32.14 CPU and Vulkan runtime, embedded in
  the ISO and run as `plebian-os-ollama.service` on `127.0.0.1:11434`, with no
  model weights.
- **Models in the 0.2.3 image:** the nine-model default bundle, the LFM2 Kilix
  Ask command model, Basic Pitch and Demucs. Other models, including the Help
  adapter and the Whisper dictation models, are first-use downloads. Each
  model's licence record and notices are under
  [`releases/0.2.3-model-compliance/`](releases/0.2.3-model-compliance/).
- **Optional, never run automatically:** `plebian-os-nvidia-driver`, the
  Ollama and diarization converter installers and the Vulkan TTS installer.

Further apps and games install on demand from the
[Kilix content catalog](https://github.com/itsmygithubacct/kilix-content#readme).
The 0.2.2 selection is [`releases/0.2.2.env`](https://github.com/itsmygithubacct/plebian-os/blob/v0.2.2/releases/0.2.2.env)
at the `v0.2.2` tag. The [components page](docs/components.md) maps every
repository to how it ships.

## Requirements

- An AMD64 machine; 4 GiB RAM is the release-tested installation baseline,
  because first boot compiles the Kilix fork.
- A GPU with a KMS/DRM driver, or llvmpipe software GL as a fallback.
- A network connection on first boot.
- For building media: `xorriso`, GNU `cpio`, `gzip`, `gpgv` and
  `debian-archive-keyring`.

Configuration files, desktop-provider variables and release-mode build inputs
are described in [docs/configuration.md](docs/configuration.md).

## Watch the series

https://github.com/user-attachments/assets/af5c8cf1-f336-42c2-bbec-e78fdc9ce64d

**[Kilix, Pleb, and Plebian-OS: A Desktop Built Inside a Terminal](https://github.com/itsmygithubacct/plebian-os/releases/download/media-v1/kilix-pleb-plebian-os-complete.mp4)**
is a ten-part tour of the whole stack, published as a
[media release](https://github.com/itsmygithubacct/plebian-os/releases/tag/media-v1).
Part one plays above; every part, with its chapters, is in
[docs/video-series.md](docs/video-series.md).

## Documentation

| File | Contents |
|---|---|
| [docs/installation.md](docs/installation.md) | How install and first boot work, the full first-boot step list, converting an existing Debian, building ISO and USB media |
| [docs/desktop.md](docs/desktop.md) | Thermal status, session logging, Tmux Manager and PTY Sessions |
| [docs/updates.md](docs/updates.md) | What `plebian-os-update` changes, its transaction and rollback, the upgrade baseline |
| [docs/configuration.md](docs/configuration.md) | Requirements in full, `closure.env` and `session.env`, desktop providers, release-mode build variables, Debian sources |
| [docs/layout.md](docs/layout.md) | Repository layout and the provenance records an install keeps |
| [docs/nvidia-driver.md](docs/nvidia-driver.md) | The optional NVIDIA driver helper |
| [docs/overview.md](docs/overview.md) | The long introduction, and Plebian-OS compared with the console-only Plebian |
| [docs/release-notes.md](docs/release-notes.md) | The 0.2.3 RC and 0.2.2 status sections that used to open this README |
| [docs/video-series.md](docs/video-series.md) | The ten-part video series |
| [docs/components.md](docs/components.md) | Every repository behind Plebian-OS and how it reaches a user |
| [UPGRADING.md](UPGRADING.md) | Supported upgrade paths, what an upgrade preserves, rollback contract, operator procedure |
| [RELEASING.md](RELEASING.md) | How a coordinated release is cut, tagged and published |
| [CHANGELOG.md](CHANGELOG.md) | Changes by release |
| [releases/README.md](releases/README.md) | The release manifest format; each release's `.env`, notes and records |
| [build/build_usb_image.md](build/build_usb_image.md) | `build_usb_image.py`: USB install sticks and their safety checks |
| [build/build_vm_image.md](build/build_vm_image.md) | `build_vm_image.py`: automated VM images |
| [build/verify-model-integration.md](build/verify-model-integration.md) | Checking a model-consumer proposal against local evidence |
| [provision/NATIVE-RUNTIME.md](provision/NATIVE-RUNTIME.md) | The native package transaction contract |
| [assets/installer/README.md](assets/installer/README.md) | Installer artwork sources, generation and attribution |
| [assets/desktop/README.md](assets/desktop/README.md) | The desktop wallpaper |

## Related repositories

- [pleb](https://github.com/itsmygithubacct/pleb#readme): the login session and
  the `pleb` CLI that installs and updates the stack.
- [kilix](https://github.com/itsmygithubacct/kilix#readme): the terminal that is
  the desktop; it pins the optional desktops and its own submodules.
- [kilix-95](https://github.com/itsmygithubacct/kilix-95#readme): the default
  desktop provider.
- Pinned in the release manifest: [kilix-system-monitor](https://github.com/itsmygithubacct/kilix-system-monitor#readme), [kilix-desktop-sdk](https://github.com/itsmygithubacct/kilix-desktop-sdk#readme), [kilix-icewm](https://github.com/itsmygithubacct/kilix-icewm#readme), [kilix-media-sdk](https://github.com/itsmygithubacct/kilix-media-sdk#readme), [kilix-waydroid](https://github.com/itsmygithubacct/kilix-waydroid#readme), [kilix-secrets](https://github.com/itsmygithubacct/kilix-secrets#readme), [kilix-voice](https://github.com/itsmygithubacct/kilix-voice#readme), [kilix-license](https://github.com/itsmygithubacct/kilix-license#readme), [kilix-mpv](https://github.com/itsmygithubacct/kilix-mpv#readme) and [kilix-encodec](https://github.com/itsmygithubacct/kilix-encodec#readme).
- Optional desktops pinned through Kilix: [kilix-cap](https://github.com/itsmygithubacct/kilix-cap#readme), [kilix-tui-utils](https://github.com/itsmygithubacct/kilix-tui-utils#readme) and [kilix-land-desktop](https://github.com/itsmygithubacct/kilix-land-desktop#readme).
- Models and apps: [kilix-needle](https://github.com/itsmygithubacct/kilix-needle#readme) (Ask and its command model release), [kilix-help-llm](https://github.com/itsmygithubacct/kilix-help-llm#readme) (the Help adapter release), [kilix-amp](https://github.com/itsmygithubacct/kilix-amp#readme) and [kilix-pdf](https://github.com/itsmygithubacct/kilix-pdf#readme) (the Media Player and PDF Viewer `pleb install` sets up) and [kilix-content](https://github.com/itsmygithubacct/kilix-content#readme) (the content catalog).

## Part of Plebian-OS

This repository is the release root of Plebian-OS, a Debian install whose
desktop is [Kilix](https://github.com/itsmygithubacct/kilix#readme) running the
[Kilix 95](https://github.com/itsmygithubacct/kilix-95#readme) desktop through
[Pleb](https://github.com/itsmygithubacct/pleb#readme). Its installer ISO,
first-boot provisioner and release manifests are how every other repository
reaches a user. The map of every repository and how it ships is on the
[components page](docs/components.md).

## License

Except where a file says otherwise, Plebian-OS code and project documentation
are released under the [MIT License](LICENSE). The installer and desktop
artwork listed in
[`assets/installer/ATTRIBUTION.md`](assets/installer/ATTRIBUTION.md) are
separate works distributed under `GPL-2.0-or-later`; the complete license text
is in [`assets/COPYING.GPL-2`](assets/COPYING.GPL-2). Components supplied by
Debian or fetched from Pleb, Kilix, and other upstream projects retain their own
licenses.
