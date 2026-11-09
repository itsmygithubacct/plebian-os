# Plebian-OS components

This page maps the public repositories behind Plebian-OS to how each one reaches a
user. Pins are those of the 0.2.3 release candidate, tag `v0.2.3-rc6`
([`releases/0.2.3.env`](../releases/0.2.3.env)); the published 0.2.2 release is
[`releases/0.2.2.env`](https://github.com/itsmygithubacct/plebian-os/blob/v0.2.2/releases/0.2.2.env)
at the `v0.2.2` tag. Every repository listed is under
[github.com/itsmygithubacct](https://github.com/itsmygithubacct); each name links to
its README.

## How an install comes together

```
installer ISO (this repo: build/remaster-iso.sh over the Debian 13 netinst)
  │  carries: preseed, provisioner, updater, Ollama runtime, default models
  ▼
Debian installer ─▶ late_command installs plebian-os-provision.sh + firstboot unit
  ▼
first boot: plebian-os-firstboot.service ─▶ plebian-os-provision.sh
  ├─ apt packages, uv, release assets (libkilix-encodec, kilix-mpv, Qt runtime)
  ├─ clone pleb @ PLEB_REF ─▶ pleb install
  │     ├─ clone kilix @ KILIX_REF (+ 9 submodules) and build its kitty fork
  │     ├─ clone kilix-95 @ KILIX95_REF (the desktop provider)
  │     └─ install the PTY broker, kilix-tui-utils, tmux-tui + tb, Kilix Voice,
  │        kilix-amp and kilix-pdf at pins held in Kilix
  ├─ kilix app install kilix-needle; kilix-secrets; the release-pinned components
  ├─ the models carried in the image (standard policy, receipts recorded)
  ├─ Kilix Playalong's three default models, unless declined
  └─ register the "Pleb" LightDM session, start the Ollama service
  ▼
login: Pleb session ─▶ one screen-filling Kilix ─▶ Kilix 95 on page 1
  ▼
on demand: kilix install <id> · kilix app run <id> · kilix games play <id>
           kilix models install <id> (licence shown, receipt recorded first)
```

Updates move every pin together: `pleb update --to <version>` (or `--latest`)
selects a release closure and, on an image, hands over to `plebian-os-update`, which
updates the OS layer, Pleb, Kilix and Kilix 95 as one transaction with rollback. See
[updates.md](updates.md).

## 1. Release roots

Cloned on first boot at the commits named in the release file.

| Repository | 0.2.3-rc6 pin | Role |
|---|---|---|
| [plebian-os](https://github.com/itsmygithubacct/plebian-os#readme) | `2283b1ae` (`v0.2.3-rc6`) | installer image, first-boot provisioner, OS updater, release manifests |
| [pleb](https://github.com/itsmygithubacct/pleb#readme) | `92c81c0e` | the LightDM session and the `pleb` command: install, session, updates |
| [kilix](https://github.com/itsmygithubacct/kilix#readme) | `beb39587` | the terminal that is the desktop: pages, panes, status bar, catalog, `kilix` commands |
| [kilix-95](https://github.com/itsmygithubacct/kilix-95#readme) | `44525e24` | the default desktop provider drawn inside Kilix (95 and XP flavors) |

## 2. Built into Kilix

Submodules of Kilix at `beb39587`, built or imported with it.

| Repository | Pin | What it does in Kilix |
|---|---|---|
| [kitty](https://github.com/itsmygithubacct/kitty#readme) (`src`) | `04c3528c` | the engine: a kitty 0.48.2 fork that draws the pane buttons, page strip and status items |
| [kitty-pty-broker](https://github.com/itsmygithubacct/kitty-pty-broker#readme) | `a5a5f2d3` | one broker per normal pane (overlays are ordinary children; `KILIX_PTY_BROKER=0` turns it off), so panes survive a frontend crash; writes the session logs |
| [kitty-frame-presenter](https://github.com/itsmygithubacct/kitty-frame-presenter#readme) | `7e201935` | presents application panes, the in-pane browser and the Kilix 95 desktop through the Kitty graphics protocol |
| [kilix-content](https://github.com/itsmygithubacct/kilix-content#readme) | `c8f0b0f5` | the pinned catalog of applications, games, tools and models, and its installer |
| [kilix-state](https://github.com/itsmygithubacct/kilix-state#readme) | `1fe26a35` | crash-safe bounded state storage for games, desktops and apps |
| [kilix-telemetry](https://github.com/itsmygithubacct/kilix-telemetry#readme) | `11f51d94` | the shared CPU, memory, pressure and thermal sampler behind the status items |
| [kilix-transcript-clean](https://github.com/itsmygithubacct/kilix-transcript-clean#readme) | `f46c55f0` | turns pane session logs into readable text (`kilix transcript`) |
| [kilix-multiplexer](https://github.com/itsmygithubacct/kilix-multiplexer#readme) | `d6989697` | semantic remoting of a Kilix session (`kilix remote`) |
| [kilix-ralph](https://github.com/itsmygithubacct/kilix-ralph#readme) | `2c42a16c` | idle-only session mailboxes and recurring follow-ups (`kilix ralph`) |

## 3. Pinned in the release file

Named in `releases/0.2.3.env`. The image builder checks each pin is a full commit and
records it in the image manifest; what happens next differs per repository.

| Repository | Pin | How it reaches the system | Role |
|---|---|---|---|
| [kilix-secrets](https://github.com/itsmygithubacct/kilix-secrets#readme) | `da05600d` | built into `/usr/local` at first boot; per-user socket enabled | the per-user encrypted credential vault (`kilix-secrets`) |
| [kilix-voice](https://github.com/itsmygithubacct/kilix-voice#readme) | `1a4e63b1` | installed at first boot for read-aloud only (`kilix voice install --without-dictation`); the small English dictation models come from the image's model bundle (§4), and Kilix 95 offers `kilix stt --setup-default` to set dictation up | read-aloud and dictation behind the speaking-head and microphone buttons |
| [kilix-system-monitor](https://github.com/itsmygithubacct/kilix-system-monitor#readme) | `9316bc26` | Kilix fetches the same commit on first use | hardware facts, the model sizer and the device lease that decide which models fit |
| [kilix-icewm](https://github.com/itsmygithubacct/kilix-icewm#readme) | `f6f52b04` | Kilix installs the same commit on first use of `kilix icewm` | the IceWM provider: a conventional window manager inside Kilix, menu built from the catalog |
| [kilix-waydroid](https://github.com/itsmygithubacct/kilix-waydroid#readme) | `9d1803df` | catalog id `kilix-waydroid`; not pre-installed (`PLEBIAN_OS_INSTALL_WAYDROID=0`) | Android sessions in a pane; its first-use runtime install needs a root-owned Plebian-OS helper, which updates stage but a fresh 0.2.3 install does not (known issue) |
| [kilix-license](https://github.com/itsmygithubacct/kilix-license#readme) | `f8486ed3` | used when the image is built (model-compliance carrier); users run the copy vendored in kilix-content | licence records, the first-use licence screen and receipts |
| [kilix-desktop-sdk](https://github.com/itsmygithubacct/kilix-desktop-sdk#readme) | `88001d74` | recorded only; nothing installs it in 0.2.3 | the desktop parent repository: the provider contract, Kilix 95, Cap, Land and kilix-tui-utils with their histories |
| [kilix-media-sdk](https://github.com/itsmygithubacct/kilix-media-sdk#readme) | `0b2b092d` | recorded only; nothing installs it in 0.2.3 | media parent repository; today it holds kilix-acoustic-link (data over sound) |

Release assets fetched by checksum on first boot:

| Asset | From | Role |
|---|---|---|
| `libkilix-encodec` 0.1.5 `.deb` | [kilix-encodec](https://github.com/itsmygithubacct/kilix-encodec#readme) release `native-deb-rc5` (source `320ce65b`) | the native EnCodec library and converter runtime |
| `kilix-mpv` 0.40.0+kilix.7 `.deb` | [kilix-mpv](https://github.com/itsmygithubacct/kilix-mpv#readme) release (source `d743a367`) | the terminal media player used by Kilix Amp and `kilix video`; the Kilix for Windows catalog builds it from `1510f72f` |
| EnCodec converter bundle | [kilix-encodec](https://github.com/itsmygithubacct/kilix-encodec#readme) release `converters-0.2.2-test.1` | the 24 kHz and 48 kHz converter runtimes, installed into `/usr/lib/plebian-os/kilix-encodec/` by the root helper `plebian-os-install-encodec-converter`; a required step |
| Qt runtime bundle | plebian-os release `qt-runtime-rc6` | Qt libraries for the applications that need them |
| diarization converter (optional) | [kilix-transcribe](https://github.com/itsmygithubacct/kilix-transcribe#readme) release `rc6-diarization-converter-20261014` | conversion software for speaker diarization, installed by the root helper `plebian-os-install-diarization-converter`; no models |

## 4. Installed at first boot at pins held in Kilix or Pleb

| Repository | Pin | How | Role |
|---|---|---|---|
| [kilix-tui-utils](https://github.com/itsmygithubacct/kilix-tui-utils#readme) | `b6321de9` | `pleb install` | the built-in applications (File Manager, System Center, Settings, Software Center, Notepad and more), the Pane Center and the Kilix TUI desktop |
| [tmux-tui](https://github.com/itsmygithubacct/tmux-tui#readme) | `e442022e` | `kilix tmux --install-only --with-tb` | Tmux Sessions (the app's own title is Tmux Manager), with [tmux-cli](https://github.com/itsmygithubacct/tmux-cli#readme) `c1c9a3ff` as the `tb` command |
| [kilix-amp](https://github.com/itsmygithubacct/kilix-amp#readme) | `eff203a7` | `kilix amp --install-only` | the Media Player |
| [kilix-pdf](https://github.com/itsmygithubacct/kilix-pdf#readme) | `d59ff451` | `kilix pdf-view --install-only` | the PDF Viewer |
| [kilix-needle](https://github.com/itsmygithubacct/kilix-needle#readme) | `a887e2fa` | `kilix app install kilix-needle` | plain-language requests (`kilix ask`, the request overlay); its command model is carried in the ISO, and [kilix-ml](https://github.com/itsmygithubacct/kilix-ml#readme) is installed inside it |

Both `pleb install` steps are best effort: if one fails, the program builds the first
time its command runs.

The image carries three model payloads, all installed without a network:

- `default-models-0221.tar.xz`, a nine-asset bundle that
  `provision/install-default-models.py` installs at first boot under the standard
  distribution policy (receipts are recorded, no licence screen is shown): the two
  object-detector sizes used by kilix-yolox, the sound-event model used by
  kilix-sound-detect, the small English dictation models used by kilix-voice, the
  Female-02 voice used by kilix-piper-tts, and three kilix-needle command models.
- the 1.36 GB archive of the default Ask command model, staged for kilix-needle
  (updates stage it with administrator rights).
- the stem-separation weights archive that Kilix Playalong uses.

First boot also installs Kilix Playalong's three default models
(stem separation, pitch detection and transcription) unless the model wizard's Playalong
page or `KILIX_PLAYALONG_MODELS=0` declined them; two come from the image and one is
downloaded. The Playalong application itself installs on demand from the catalog.

## 5. Installed on first use at pins held in Kilix

Kilix clones each into `~/.local/gpu_terminal/sources/` and builds it the first time
the command that needs it runs.

| Repository | Pin | Started by | Role |
|---|---|---|---|
| [kilix-cap](https://github.com/itsmygithubacct/kilix-cap#readme) | `84906fa6` | `kilix cap` | the Cap desktop provider: a mansion of rooms drawn in C |
| [kilix-land-desktop](https://github.com/itsmygithubacct/kilix-land-desktop#readme) | `8e34fd94` | `kilix land` | the Land desktop provider: an avatar in a house with a hotbar |
| [kilix-chawan](https://github.com/itsmygithubacct/kilix-chawan#readme) | `b2b29324` | `kilix chawan` | the text-mode web browser |
| [kilix-piper-tts](https://github.com/itsmygithubacct/kilix-piper-tts#readme) | `ad84b296` | the first Kilix 95 desktop start (`kilix wizard install-default-voice`), or `kilix tts --install=kilix-female-02` | the sandboxed neural voice provider; its Female-02 voice is in the image's bundle |
| [kilix-whisper-stt](https://github.com/itsmygithubacct/kilix-whisper-stt#readme) | `15ef23b3` | `kilix voice whisper` | local dictation models; an online update also downloads the medium English model as a Playalong default |
| [kilix-bonsai](https://github.com/itsmygithubacct/kilix-bonsai#readme) | `630da3cf` | `kilix bonsai` (Model Store) | local model folders and their store |
| [kilix-yolox](https://github.com/itsmygithubacct/kilix-yolox#readme) | `fa085fae` | `kilix install yolox` (clones the repository and builds a virtualenv) | the object detector that Image Analyzer and Camera Recorder call |
| [kilix-sound-detect](https://github.com/itsmygithubacct/kilix-sound-detect#readme) | `a492176c` | `kilix yamnet install` (needs the copy inside an installed Camera Recorder or Image Analyzer; builds a virtualenv) | sound-event detection for Camera Recorder and Image Analyzer |
| [kilix-mask](https://github.com/itsmygithubacct/kilix-mask#readme) | `476bc1d6` | `kilix mask`, the Region Painter app | region maps painted over an image, for camera zones and walkable space |
| [kilix-qwen-tts](https://github.com/itsmygithubacct/kilix-qwen-tts#readme) | `9b0c08a3` | `kilix tts provider prepare` | a sandboxed text-to-speech provider, a review candidate; its models download on first use |
| [kilix-transcribe](https://github.com/itsmygithubacct/kilix-transcribe#readme) | `52501284` | `kilix transcribe prepare` | a CPU transcription provider, a development runtime |

## 6. The content catalog

`kilix install` lists the catalog in `kilix-content` (`c8f0b0f5`, schema 4): 37
applications, 16 games, 2 tools and 43 model assets. Entries built from source:

| Catalog id | Repository | Pin |
|---|---|---|
| `kilix-amp` | [kilix-amp](https://github.com/itsmygithubacct/kilix-amp#readme) | `eff203a7` |
| `kilix-claudex` | [kilix-claudex](https://github.com/itsmygithubacct/kilix-claudex#readme) | `8346512b` |
| `kilix-find` | [kilix-find](https://github.com/itsmygithubacct/kilix-find#readme) | `3fa55931` |
| `kilix-graphs` | [kilix-graphs](https://github.com/itsmygithubacct/kilix-graphs#readme) | `720af007` |
| `kilix-help-llm` | [kilix-help-llm](https://github.com/itsmygithubacct/kilix-help-llm#readme) | `4abc52e9` |
| `kilix-needle` | [kilix-needle](https://github.com/itsmygithubacct/kilix-needle#readme) | `a887e2fa` |
| `kilix-nvr` | [kilix-nvr](https://github.com/itsmygithubacct/kilix-nvr#readme) | `e68b5d14` |
| `kilix-object-detect` | [kilix-object-detect](https://github.com/itsmygithubacct/kilix-object-detect#readme) | `ee8ca067` |
| `kilix-pdf` | [kilix-pdf](https://github.com/itsmygithubacct/kilix-pdf#readme) | `d59ff451` |
| `kilix-pdf-conversion` | [kilix-pdf-conversion](https://github.com/itsmygithubacct/kilix-pdf-conversion#readme) | `e841241b` |
| `kilix-power-controls` | [kilix-power-controls](https://github.com/itsmygithubacct/kilix-power-controls#readme) | `6558f802` |
| `kilix-rtsp` | [kilix-rtsp](https://github.com/itsmygithubacct/kilix-rtsp#readme) | `bf5128f2` |
| `kilix-techno` | [kilix-techno](https://github.com/itsmygithubacct/kilix-techno#readme) | `0992edcb` |
| `kilix-waydroid` | [kilix-waydroid](https://github.com/itsmygithubacct/kilix-waydroid#readme) | `9d1803df` |
| `playalong` | [kilix-playalong](https://github.com/itsmygithubacct/kilix-playalong#readme) | `a11a0219` |
| 12 games | [kilix-games](https://github.com/itsmygithubacct/kilix-games#readme) | `668faacf` |
| `kilix-land` | [kilix-land](https://github.com/itsmygithubacct/kilix-land#readme) | `710d73ef` |
| `pleb-tower` | [pleb-tower](https://github.com/itsmygithubacct/pleb-tower#readme) | `9e4595ee` |
| `super-kilix` | [super-kilix](https://github.com/itsmygithubacct/super-kilix#readme) | `e47f6687` |
| `kilix-encodec-convert-24khz`, `-48khz` | [kilix-encodec](https://github.com/itsmygithubacct/kilix-encodec#readme) | `22290fb4` |

`kilix content` searches a saved-source index through kilix-find. The games in
kilix-games are Bashed Earth, Chess Bash, Joustix, Kilix Fishtank,
Kilix JPAK, Kilix Lights, Kilix Pong, Kilix Rancher, Kilix Brokeout, Solitaire TUI,
Kilix Lander and Tic-Tac-Toe. The built-in applications (File Manager, Notepad,
System Center, Settings, Software Center, Session Center, Calculator, Weather and
others) come from the one pinned kilix-tui-utils package. Doom and DOSBox use a
DOSBox found on the system or a downloaded dosbox-staging.

Models install with `kilix models install <id>`, which shows the licence and records
a receipt before downloading. The models carried in the image (§4) are installed
under the standard distribution policy, which records their receipts without a
licence screen; Plebian-OS carries no model weights it did not record a licence
for. kilix-transcribe offers two assets, the second being the CPU diarization model
`kilix-diarization-cpu`. Their providers are kilix-needle, kilix-bonsai, kilix-ollama,
kilix-voice, kilix-qwen-tts, kilix-object-detect, kilix-pdf-conversion,
kilix-transcribe, kilix-whisper-stt, kilix-piper-tts, kilix-encodec,
kilix-playalong and kilix-sound-detect, plus two providers built into Kilix
(`kilix-split` and `paradee`).

## 7. Libraries compiled into the above

| Repository | Used by |
|---|---|
| [kilix-game-sdk](https://github.com/itsmygithubacct/kilix-game-sdk#readme) | kilix-games, pleb-tower, super-kilix, pleb-plant-grower, kilix-land, kilix-cap, kilix-land-desktop, kilix-desktop-sdk, kilix-land-agent |
| [kitty-terminal-session](https://github.com/itsmygithubacct/kitty-terminal-session#readme) | kilix-game-sdk, kilix-techno, kilix-pdf, kilix-playalong, kilix-rtsp, kilix-sound-detect, kilix-mask, kilix-cap, kilix-land-desktop, kilix-land-agent and kilix-desktop-sdk through kilix-game-sdk |
| [kitty-framebuffer](https://github.com/itsmygithubacct/kitty-framebuffer#readme), [kitty-input](https://github.com/itsmygithubacct/kitty-input#readme) | kitty-terminal-session, and through it everything that uses it; kilix-pdf is the one first-boot program that compiles them |
| [soft-raster](https://github.com/itsmygithubacct/soft-raster#readme) | kilix-game-sdk, kilix-techno, kilix-playalong, kilix-rtsp, kilix-sound-detect, kilix-mask, kilix-cap, kilix-land-desktop, kilix-land-agent; kilix-nvr and kilix-object-detect through their camera and detector submodules; optional in kilix-graphs |
| [pcm-mixer](https://github.com/itsmygithubacct/pcm-mixer#readme) | kilix-game-sdk, kilix-techno, and through the SDK kilix-cap, kilix-land-desktop and kilix-land-agent |
| [chip-sequencer](https://github.com/itsmygithubacct/chip-sequencer#readme) | super-kilix, pleb-plant-grower, kilix-techno |
| [pleb-plant-grower](https://github.com/itsmygithubacct/pleb-plant-grower#readme) | kilix-land (its conservatory) |
| [kilix-ml](https://github.com/itsmygithubacct/kilix-ml#readme) | kilix-needle |
| [kilix-state](https://github.com/itsmygithubacct/kilix-state#readme) | Kilix itself (submodule), kilix-game-sdk (its own submodule, so every game compiles its own copy), kilix-techno |
| [kilix-object-detect](https://github.com/itsmygithubacct/kilix-object-detect#readme) | kilix-nvr (submodule); also the Image Analyzer app |
| [kilix-motion-detect](https://github.com/itsmygithubacct/kilix-motion-detect#readme) | kilix-nvr, kilix-object-detect (motion gates detection) |
| [kilix-rtsp](https://github.com/itsmygithubacct/kilix-rtsp#readme) | kilix-nvr, kilix-object-detect; also the Camera Viewer app |
| [kilix-sound-detect](https://github.com/itsmygithubacct/kilix-sound-detect#readme) | kilix-nvr, kilix-object-detect |
| [kilix-mask](https://github.com/itsmygithubacct/kilix-mask#readme) | kilix-nvr (zones), kilix-land-desktop (walkable space) |
| [kilix-license](https://github.com/itsmygithubacct/kilix-license#readme) | vendored in kilix-content and kilix-encodec |

## 8. Other public repositories

Not installed by Plebian-OS, or used only for building and testing it.

| Repository | What it is |
|---|---|
| [kilix-llm](https://github.com/itsmygithubacct/kilix-llm#readme) | local CPU model inference and the help-model build; standalone |
| [kilix-ollama](https://github.com/itsmygithubacct/kilix-ollama#readme) | the Ollama mediation CLI; listed in the Kilix for Windows catalog |
| [kilix-tmux](https://github.com/itsmygithubacct/kilix-tmux#readme) | socket-explicit tmux control; Kilix vendors a derivative as `kilix_tmux` |
| [tmux-browse](https://github.com/itsmygithubacct/tmux-browse#readme) | tmux dashboard with embedded ttyd; listed in the Kilix for Windows catalog |
| [paneline](https://github.com/itsmygithubacct/paneline#readme) | one-line typed messages between agent panes |
| [kilix-agent-bench](https://github.com/itsmygithubacct/kilix-agent-bench#readme) | agent task evaluation in disposable VMs |
| [python-sound-generator](https://github.com/itsmygithubacct/python-sound-generator#readme) | the `soundgen` CLI; regenerates the sound banks of pleb-tower and kilix-land-desktop (`make audio`, not the normal build); a Kilix for Windows app |
| [dosbox-kilix](https://github.com/itsmygithubacct/dosbox-kilix#readme) | DOSBox-X with Kitty and ANSI output; built by the Kilix for Windows catalog |
| [kilix-land-agent](https://github.com/itsmygithubacct/kilix-land-agent#readme) | a Land studio room with a resident that proposes checked actions; listed in the Kilix for Windows catalog |
| [kilix-desktop-contract](https://github.com/itsmygithubacct/kilix-desktop-contract#readme) | provider protocol v1: schemas, a C11 header and a validator; the maintained copy is in kilix-desktop-sdk |
| [plebdroid](https://github.com/itsmygithubacct/plebdroid#readme) | an Android APK carrying the Kilix 95 desktop and a Debian userspace; no release yet |
| [kilix-voicebox](https://github.com/itsmygithubacct/kilix-voicebox#readme) | a candidate voice studio over kilix-qwen-tts and kilix-transcribe; runs no inference itself |
| [kilix-voicegen](https://github.com/itsmygithubacct/kilix-voicegen#readme) | an in-development C++17 speech engine; developer tools in the Kilix for Windows catalog |
| [kilix-image-shop](https://github.com/itsmygithubacct/kilix-image-shop#readme) | the core of a non-destructive image editor over GEGL/babl; listed in the Kilix for Windows catalog |
| [kilix-background-remover](https://github.com/itsmygithubacct/kilix-background-remover#readme) | a candidate image and video cutout provider; listed in the Kilix for Windows catalog |
| [kilix-compress](https://github.com/itsmygithubacct/kilix-compress#readme) | verified, non-overwriting compression: library, CLI and a small window |
| [kilix-bench](https://github.com/itsmygithubacct/kilix-bench#readme) | offscreen frame-path benchmarks for Kilix rendering |
| [kilix-testkit](https://github.com/itsmygithubacct/kilix-testkit#readme) | placeholder for a shared test harness |
