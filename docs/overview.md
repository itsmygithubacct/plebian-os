# Plebian-OS overview

This is the introduction that opened the README before it became a short entry
point. The [README](../README.md) has the current summary.

**A regular Debian install whose desktop is [Pleb](https://github.com/itsmygithubacct/pleb) —
a single screen-filling [Kilix](https://github.com/itsmygithubacct/kilix), with
its clickable chrome visible, as the whole session — in place of XFCE.**

Plebian-OS is stock Debian in every way except the "desktop": where a normal
Debian+XFCE install would give you a panel and a full desktop environment, Plebian-OS logs
you into one screen-filling Kilix (a Tilix-styled kitty fork: clickable pane buttons,
splits, pages, images, and desktop providers that open in Kilix tabs). The
login default is the main Kilix instance with Kilix 95 loaded as its first
page. Its 95 flavor is explicit; Kilix Cap and Kilix TUI are Kilix-pinned optional
desktops, Kilix Land is a Kilix-pinned optional walkable desktop, and Kilix
IceWM provides a conventional window-manager desktop inside Kilix's private X
session. Provisioning adds the selected Pleb and Kilix components to a regular
Debian system using the coordinated source and artifact pins:

```
Debian installer  ─▶  provision the selected stack  ─▶  Pleb session
 (no desktop task)       (Pleb, Kilix and providers)    (visible Kilix chrome)
```

The selected Pleb session supplies account locking and power services,
monitor scaling, device setup controls, and Pleb's user-selected X11 capture
portal. Capture uses PipeWire with WirePlumber's `video-only` profile; PulseAudio
continues to handle audio. The locally built capture transport supplies
descriptor-backed video buffers. Pleb documents bounded Firefox ESR and Chromium
capture evidence, including user consent and Stop sharing. These component
checks do not establish physical desktop acceptance; the published release
notes below define the installed-release qualification scope.

The release notes that paragraph refers to are in
[release-notes.md](release-notes.md); each release keeps its own notes under
[`releases/`](../releases/).

## Plebian-OS vs. Plebian

The sibling **plebian** project is the *console-only* take: no X, no display
manager — kilix runs on the bare virtual terminals via a per-VT cage compositor,
`Ctrl+Alt+F1…F11` switching between independent kilix VTs. **Plebian-OS** is the
*graphical desktop* take: a normal LightDM login whose session is a
screen-filling Kilix with its own controls visible (via Pleb + Xorg). Same
spirit — "a machine whose desktop is Kilix" — reached the way a desktop distro does it (display manager + X session)
rather than by replacing the console. Pick plebian for a headless/console box,
Plebian-OS for a desktop-shaped one.
