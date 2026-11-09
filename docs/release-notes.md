# Release notes from the README

These sections stood at the top of the README until 2026-11-09. The
authoritative record of each release is its notes file under
[`releases/`](../releases/) (for 0.2.3:
[0.2.3-notes.md](../releases/0.2.3-notes.md) and
[0.2.3-followups.md](../releases/0.2.3-followups.md)), the
[changelog](../CHANGELOG.md) and the [GitHub Releases
page](https://github.com/itsmygithubacct/plebian-os/releases).

## 0.2.3 RC5 Ask default

This RC5 image-models branch includes **LFM2 Kilix revision .9**
(`lfm2-kilix-v5e1-wse-20261106.9`) as the Kilix Ask default. The installer
includes its verified 1.36 GB archive; upgrades stage
the same pinned archive using their existing admin context. Original licence
documents are installed under
`/usr/local/share/doc/plebian-os/models/lfm2-kilix-commands-20261106-v9/notices/`.
A new install or upgrade then installs that staged archive for the desktop
user. By the owner's 2026-11-07 determination, its published custom terms,
including the commercial-use limitation, are a notice, as with a Debian
non-free package: they are shipped with the model, and installation records a
notice receipt that claims no agreement. The receipt is created on the machine.
It is not shipped in the image, and the terms are not waived. Explicit model
preferences remain in effect, and the previous `20261104-v8` directory is
retained for rollback. The archive is published as release
`lfm2-kilix-commands-20261106-v9` of kilix-needle. See the
[command-model selection](../releases/0.2.3-command-model.json)
for exact hashes, source pins, results and limitations.

The image also includes **Basic Pitch** (`basic-pitch-icassp-2022-onnx`).
The same new install and upgrade install its archive under the standard
licence policy. The nine-model default bundle is unchanged.

## 0.2.3 RC4 Help default

The 0.2.3 RC4 candidate includes **kilix-qwen-sft1-2b** as the default local
Help model. Ask everyday questions about using Kilix and Plebian-OS and receive
a command, a brief explanation and related documentation links:

```sh
kilix help-setup
kilix help-answer "How do I launch a Kilix pane?"
kilix help-answer "How do I list panes?"
kilix help-answer "How do I launch agents?"
kilix help-answer "How do I use the TUI?"
```

Setup explicitly downloads about 4.6 GB of model files plus the CPU runtime,
after checking memory and storage. A GPU is not required. For documentation
passages without model setup, use `kilix help-search "How do I list panes?"`.
Help does not inspect live machine state or execute its suggested commands.

See the [Help setup and troubleshooting guide](https://github.com/itsmygithubacct/kilix/blob/6b6dbda8d75fe787b6e3bdfaac597980251fd03c/docs/help/answers.md)
and the [0.2.3 release notes](../releases/0.2.3-notes.md). The Help selection
record pins source `4abc52e9236899a05738807d32a3431270b6a3c2` and the published
adapter release `kilix-qwen-sft1-2b`. Final OS image and update qualification
remain pending. The sections below retain the 0.2.2 baseline and component
status; the 0.2.3 notes describe the newer selections and bundled models.

## Release 0.2.2 — Linux

Published November 3, 2026 for Debian 13 (trixie), AMD64. The release includes
managed coding sessions, persistent PTY controls, durable agent mailboxes,
refreshed desktop providers, inline media repairs, and installer/update
recovery fixes. It includes `xorriso` and fixes administrator password entry
in the Kilix-95 optional-software wizard. Fresh installation media carries the
Ollama 0.32.14 CPU/Vulkan runtime; no model weights are bundled or downloaded
during provisioning. Updating from 0.2.1 does not install that runtime carrier.

- [Download the 964 MiB installer ISO](https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/plebian-os-0.2.2-amd64.iso).
- [Published checksums](https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/SHA256SUMS).
- [Release notes and known issues](https://github.com/itsmygithubacct/plebian-os/releases/tag/v0.2.2).
- [Exact release manifest](https://github.com/itsmygithubacct/plebian-os/blob/v0.2.2/releases/0.2.2.env) and [upgrade policy](https://github.com/itsmygithubacct/plebian-os/blob/v0.2.2/UPGRADING.md).

Linux installation and lifecycle qualification covers QEMU/KVM BIOS and EFI
virtual machines. Bare-metal USB installation and physical GPU operation were
not qualified. Windows remains at `windows-v0.2.2-preview.4`; ARM64 is not a
supported OS release target. See the [published release notes](https://github.com/itsmygithubacct/plebian-os/releases/tag/v0.2.2)
for known issues and deferred feature qualification.

Use the immutable `v0.2.2` tag to install or reproduce this release. This
branch can contain later development; publication of a component or model
candidate does not extend the release's qualification.

The selected binary artifacts target **AMD64**. ARM64 support is under
development; architecture checks in the Qt, media, converter and other runtime
paths must pass with matching artifacts before an ARM64 upgrade is supported.
Native ARM64 Qt, MPV and inference runtime candidates are now published for
review and isolated testing. They do not select an ARM64 release or enable an
ARM64 upgrade; the [release notes](../releases/0.2.2-notes.md) record their scope.
The Waydroid application is provisioned from its exact selected revision into
root-owned managed paths, with source and provenance records and transactional
upgrade/rollback coverage. The shared Content catalog exposes its single-instance
Android entry. The separate checksummed first-use helper installs the Android
runtime only on explicit request; OS provisioning does not download Android
images. Installed-target, Android and physical acceptance remain open; the
selected first-use runtime closure supports AMD64 only.

The dependency manifest supplies
the same compression providers, read-only hardware-discovery tools, and
`linux-perf` qualification package to the preseed and standalone provisioning
paths. Their manifest parity is covered by repository tests. The image includes
the Vulkan loader and Mesa ICDs for the installed Ollama runtime;
`--vulkan-nouveau` remains the opt-in that adds Nouveau firmware. The pinned
ggml Vulkan backend ignores CPU Vulkan devices during default device selection,
so a machine without a hardware GPU uses Ollama's CPU backend. Combining a
Vulkan mode with `--qualification` adds `vulkaninfo`.

Pocket TTS conversion and its persistent Vulkan runtime are separate explicit
opt-ins. The image ships neither model weights nor generated GGUF files.
Prepare their exact Debian prerequisites and install the two source closures
with:

```sh
sudo plebian-os-install-deps --vulkan-tts
sudo plebian-os-install-ollama-converter
sudo plebian-os-install-kilix-vulkan-tts
```

On Nouveau, combine `--vulkan-tts` with `--vulkan-nouveau` so the firmware
closure is present too. The dependency command selects the common Vulkan
runtime, six direct Pocket-converter pins, and the two Vulkan build pins. The
converter installer verifies one immutable llama.cpp archive, extracts a
1.6 MiB Pocket-only source tree, retains its MIT license and modification
notice, and installs a fixed offline wrapper. The measured Debian converter
closure is roughly 150 MiB to download and 0.8 GiB installed. Those Python
packages are needed only for local conversion and are not automatically
removed because another local application may share them.

The runtime installer fetches the same 36,889,653-byte source archive, builds
locally with two jobs, and admits only an independently reproduced exact
66,532,472-byte runtime closure. It needs at least 1 GiB of temporary free
space; its source archive and build tree are discarded after atomic
installation. `--archive PATH` lets both installers reuse an already downloaded
exact archive. A first request may also spend substantial time compiling the
Vulkan shader cache. None of these commands runs during provisioning,
qualification, preseed, or a plain Vulkan install. These closures remain 0.2.2
candidates, not accepted release schemas or model-publication authorization.

Plebian-OS 0.2.2 carries the approved Ollama 0.32.14 CPU + Vulkan runtime in
the ISO as a deterministic 20,689,764-byte offline archive. Provisioning checks
its release-manifest size and SHA-256, extracts its confined 107-file/10-link
closure, installs the notices under `/usr/share/doc/ollama-runtime/notices`,
publishes the OS-owned `RELEASE-DISPOSITION` beside the carrier's
`BUILD-CLOSURE` (source: `provision/ollama/RELEASE-DISPOSITION`), and enables `plebian-os-ollama.service` on `127.0.0.1:11434`. The service runs
as the `ollama` system account with model state under `/var/lib/ollama`; the
`ollama` client is available on `PATH` for the first-use model wizard.

The image carries no model weights and provisioning downloads none. The wizard
downloads a selected model only after its per-model licence step. The service
sets `OLLAMA_NO_CLOUD=1` to disable Ollama cloud features and prevent registry
identity creation; ordinary local model pulls remain available. Debian's
Vulkan loader and Mesa driver copyright notices come from their Debian packages.

The separate `kilix-ollama` app is not installed or launched by default. Its
TCP mode can claim the same loopback port if manually enabled, so its TCP
candidate must retain network-namespace isolation when the system service owns
port 11434.

The installer still accepts an exact local closure through
`plebian-os-install-kilix-ollama-runtime --closure PATH`; the ISO provisioning
path instead uses the pinned offline carrier. `--vulkan-nouveau` adds optional
firmware, while firmware is not required for the base runtime.

Release reproduction starts from that release's immutable tag, checksummed
manifest and published notes. Development source is not a supported installed
upgrade destination. Upgrade paths and preservation requirements are defined
in [UPGRADING.md](../UPGRADING.md).
