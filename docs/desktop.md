# Using the Plebian-OS desktop

Controls that are ready after the first login. The shared settings file and
both settings interfaces are described in the [Pleb settings
documentation](https://github.com/itsmygithubacct/pleb#readme).

The Kilix page strip includes a default-off thermometer that reports the
hottest readable sensor in green/yellow/red and opens `kilix-temps` in a new
tab. Firstboot builds and verifies Kilix's exact pinned dashboard and graphics
closure and publishes the command on `PATH`, so this works on a clean OS install
without a developer checkout. The volume control opens `pulsemixer`, with
`alsamixer` as a fallback. It appears immediately left of the network/Wi-Fi
control; Network remains immediately left of the calendar and opens `nmtui`.
Run `kilix-settings` (or `pleb settings`), or use Kilix 95's Settings menu, to
enable **Thermal status** and remove or re-add every top-bar item and pane-title
button. For scripts, use `kilix settings --set temperature=on`. All of those
interfaces use
`~/.local/gpu_terminal/settings.conf` as their single source of truth.

**Session logging is on by default.** Each pane's output is recorded by the PTY
broker to `~/.local/gpu_terminal/kilix/state/transcripts/<session>.log` — one
bounded 8 MiB log per pane, mode `0600`, with kitty graphics payloads replaced
by a byte-count marker so a pixel desktop cannot flood the log. Because the
broker owns the PTY, a detached, recovered, or crashed pane is still recorded,
including whatever it printed on its way out. Only output is captured; typed
input appears solely where the pane echoes it, so hidden password prompts are
not recorded. A pane's log stays plain only while that pane is live. Dead-pane
logs are compressed with `zstd -3` into a 5 GiB recent tier; the oldest are
recompressed losslessly with `zstd -9` into a separate 1 GiB archive tier, and
the oldest archives are pruned once that tier is full. These defaults leave
working headroom on the release-tested 20 GiB disk and can be changed in the
shared settings file or either settings UI.

```sh
kilix transcript                       # list recorded panes, newest first
kilix transcript show <session>        # print one
pleb status                            # current policy + how many logs exist
kilix settings --set transcript=off    # turn recording off
```

The same three controls (on/off, `elide`/`keep` graphics, and a `2M`/`8M`/`32M`/
`128M` per-pane budget) are in `kilix-settings` under **Session logging** and in
Kilix 95's Settings under **Session logs**; all of them write the shared
`~/.local/gpu_terminal/settings.conf`.

The Kilix 95 Start menu includes **Tmux Manager**. It opens in a new tab and
uses the pinned `tmux-tui` plus `tmux-cli` closure installed during firstboot.
Both `tmux-tui` and the `tb` alias are also available directly from a shell.

The same Programs menu includes **PTY Sessions**, a terminal UI for Kilix's
persistent panes. It lists detached sessions first and can attach, refresh, or
terminate one after confirmation; `kilix pty` opens it directly from a shell.
