# Plebian-OS upgrade policy

This policy starts with **Plebian-OS 0.1.7**. It is also encoded for tooling in
[`releases/upgrade-policy.json`](releases/upgrade-policy.json).

An in-development 0.2.2 checkout is not a supported upgrade destination. A
target becomes supported only when its immutable release manifest, notes,
artifacts, and adjacent-version acceptance evidence are published together.
Never point the installed updater at a development branch or use 0.2.2 source
work to modify a 0.2.1 release worktree.

## Baseline and supported paths

- Install 0.1.7 fresh when the machine runs anything older. In particular,
  0.1.2 to 0.1.7 is not a supported in-place upgrade.
- 0.1.3, 0.1.4, and 0.1.5 were not coordinated stack releases. 0.1.6 was an
  unpublished candidate. None is an upgrade source or destination.
- 0.1.7 is the first supported upgrade **source**. Each later release must
  support an in-place upgrade from the immediately previous published release,
  even when unused version numbers lie between the two releases.
- A direct upgrade which skips a published release is supported only when that
  exact start-to-target path is named in the target release notes and passes
  the same acceptance gate. Otherwise upgrade one published release at a time.

Reinstallation remains available as recovery, but it does not satisfy the
upgrade requirement for a release after 0.1.7.

## What an upgrade must preserve

A successful supported upgrade changes the coordinated release-controlled
version, refs, and immutable dependency pins together. It must preserve:

- user files and home-directory data;
- application state under `~/.local/gpu_terminal`, including desktop state,
  game saves, transcripts, and provider data;
- operator choices in `/etc/pleb/session.env` which are not release-controlled
  pins, including session, provider, storage, and kiosk choices;
- the shared `settings.conf`, including appearance, logging, thermal, audio,
  network, and game settings; and
- custom wallpaper and desktop layout selections.

A release may deliberately migrate a setting only when its release notes name
the old and new representation, the migration is tested, and rollback restores
the previous representation. Unknown keys and newer-schema data must not be
silently discarded.

Release-controlled keys include the coordinated version/release mode, every
`*_REF` source pin in the release manifest (ten as of 0.2.2, since the
system-monitor, desktop-SDK, IceWM, media-SDK and Waydroid components joined
the closure in 0.2.1), the Debian snapshot and installer input, the Kilix
engine and Go pins, and enabled optional-closure pins such as Kilix Voice. Those keys move as
one reviewed target closure; mixing old and new release pins is unsupported.

### The 0.2.0 shared-credential transition

The 0.2.0 image created the fixed `pleb` account with a documented starter
password. A 0.2.0-to-0.2.1 update must preserve the account name, password hash,
hostname, home ownership, autologin choice, and every user file; it never asks
the installer identity questions again and never rewrites the password.

During the OS-layer transaction, 0.2.1 compares the installed hash with the
historical starter password through `crypt(3)`. If it still matches and an
OpenSSH server is installed, the updater writes one root-owned OpenSSH drop-in
that disables password and keyboard-interactive authentication for that user
only. Public-key access and every other account retain their prior policy, and
the local desktop password-change warning remains available. Changing the
password through that warning removes the exact managed drop-in and reloads
OpenSSH; a different file at that path is never replaced or removed.

If the account was already hardened, remote policy is left untouched. Fresh
0.2.1 installs carry a root-owned identity-profile record and do not install
the legacy helper or its narrow sudo grant. The updater treats a malformed
identity record, ambiguous root-run legacy account, unsafe SSH path, invalid
effective SSH policy, or reload failure as an update failure. Its outer
transaction restores both the prior drop-in state and the running SSH policy.

### The 0.2.1 to 0.2.2 transition

Nothing migrates. Four things change under an upgrader, all preserved or
release-controlled by the rules above:

- `/etc/xdg-desktop-portal/pleb-portals.conf` is a new **release-managed** file,
  written inside the OS-layer transaction beside the LightDM session pin and
  removed by a rollback. It is not an operator file.
- The session now starts two `autocutsel` holders so copied text outlives the
  app that copied it. Opting out is an **operator choice**: `PLEB_CLIPBOARD=off`
  (or `=clipboard`) in `/etc/pleb/session.env` or the user's
  `~/.local/gpu_terminal/pleb/config/session.env`, both of which an upgrade
  preserves.
- `KILIX_RUN_BROWSER_PROFILE` in Kilix's `kilix.env` names a persistent browser
  profile for contained browsers. Operator choice, preserved; the profile
  directory it names lives under `~/.local/gpu_terminal` and is application
  state.
- Throwaway browser profiles under `~/.local/gpu_terminal/kilix/session/app-profiles`
  are now reaped as soon as their owning process is gone. An upgrader who had
  accumulated them will see that directory shrink on the first browser launch;
  nothing a live process owns is touched.

## Failure and rollback contract

Before its first mutation, the updater must snapshot the selected source
commits, deployed OS/Pleb files, engine generation and stamps, release-control
configuration, and every setting a migration will rewrite. If any fetch,
validation, build, install, migration, health check, or restart step fails, the
machine must select the exact previous coherent stack and configuration again.

Downloaded git objects, packages, and toolchains may remain after rollback when
they are additive and inactive. User data must never be removed as rollback
cleanup. The updater must report recovery material it could not restore and
must not report success until the outer transaction commits.

## Release gate for every version after 0.1.7

The target release is not publishable until its immediately previous published
release has been installed from the published image in a fresh VM and upgraded
using the documented installed-system path. That path must use the updater
shipped by the starting release with the target's immutable release closure; it
must not depend on an unpublished developer checkout. The acceptance run must:

1. verify the starting VM against the previous release's published hashes and
   exact coordinated commits;
2. create sentinels in user data, game/provider state, desktop state,
   `settings.conf`, and operator-owned session configuration;
3. exercise one induced mid-transaction failure and prove the old version,
   refs, runtime generation, settings, and sentinels are restored;
4. select the target closure with the target release's own
   `provision/plebian-os-select-closure.sh <x.y.z>`, run exactly as
   "Selecting a target closure" below documents, and confirm it reports every
   release-controlled key it moved; then perform the successful upgrade with
   `plebian-os-update --restart` — nothing privileged in between — reboot, and
   verify all coordinated version commands, refs, provenance, provider launches,
   and sentinels;
5. verify that release-controlled pins all moved to the target closure and that
   non-release-controlled choices did not; and
6. record the tested start version, target version, artifact hashes, exact
   commits, result, and any explicitly supported skip paths in the target
   release notes and provenance.

Passing a fresh-install test does not substitute for this upgrade test. If the
previous published image or its exact source closure cannot be reproduced, the
new release remains blocked until an equivalent immutable fixture is recovered
and documented.

## Operator procedure

Release images keep exact refs in `/etc/pleb/session.env`; running
`plebian-os-update` without selecting a new closure intentionally revalidates
the installed release rather than drifting to a branch head; the updater alone
does not select a new release closure. Every future target release must ship an
actionable release-specific mechanism or exact instructions which validate and
atomically select all of its release-controlled keys as one closure. That
mechanism must complete successfully before the operator runs:

```sh
plebian-os-update --restart
```

The mechanism is `provision/plebian-os-select-closure.sh`, and the release which
ships it is the **target** release, not the installed one: it reads
`releases/<x.y.z>.env` out of the published `v<x.y.z>` tag, so the pins are the
immutable ones that release was accepted with, whatever the machine is running
now.

### Selecting a target closure

Run this as the Pleb user on the installed machine — never through `sudo`; the
selector elevates the bounded installed-file writes it needs and refuses to run as root, as
`plebian-os-update` does. `$SRC` is the Plebian-OS source checkout the installed
system already uses; only its object store is read, so its working tree and HEAD
stay exactly where the updater expects them.

```sh
SRC="$HOME/.local/gpu_terminal/sources/plebian-os"
SEL="$(mktemp)"
git -C "$SRC" fetch --force origin 'refs/tags/v0.1.8:refs/tags/v0.1.8'
git -C "$SRC" show v0.1.8:provision/plebian-os-select-closure.sh >"$SEL"
bash "$SEL" 0.1.8
```

Substitute the target version throughout, including the fetch and `git show`.
Always execute the selector extracted from the **target** tag. The installed
release's copy may not know validation rules introduced by a newer manifest;
for example, 0.1.8's selector predates 0.1.9's exact uv pins and per-component
ancestry proof.

Beginning with 0.1.9, the selector is also the twelfth payload in the validated,
rollback-safe OS layer and is installed as `/usr/local/bin/plebian-os-select-closure`.
That installed copy provides `--show`, `--rollback`, and same-release
reselection. It is not a substitute for extracting a later target release's
own selector from that target's immutable tag.

The target selector verifies that its running bytes match that exact target
commit, then deploys both that selector and the target commit's updater while
it selects the closure. This is the first-hop bootstrap: an updater from the
previous release cannot know a system payload or final-provenance rule
introduced by its successor merely because it later replaces its own on-disk
inode. The recovery record therefore backs up `/etc/pleb/session.env`, the
installed selector, and the installed updater. A failed selection restores all
three immediately; `--rollback` restores each prior tool or removes it when the
starting image had none.

It validates the whole closure before it writes anything: a manifest which is
incomplete, malformed, still holds a placeholder, pins a branch instead of a
commit, half-pins an optional closure such as Kilix Voice, or declares a version
which disagrees with the release identifier or with the release commit's
`VERSION`, is refused and the refusal names what was wrong. It then reports every
release-controlled key it will move. It fetches each exact Plebian-OS, Pleb,
Kilix, and Kilix-95 target commit without moving a checkout, compares it with
the installed commit, and announces `DOWNGRADE` or `DIVERGED` per component;
a rising release number cannot hide a falling pin. It then proves the rendered
configuration changes nothing else. It prepares the exact target selector,
target updater, and new `/etc/pleb/session.env` beside their destinations before
replacing any of them. Either the complete selected set moves or none does; a
write that fails part way restores the previous session and both tools and says
so. `--offline`
performs the same proof only when every target object and the complete histories
are already present locally.

Useful before and after — `SEL` being whichever copy of the selector the block
above put in your hands:

```sh
bash "$SEL" 0.1.8 --dry-run   # substitute the target version
bash "$SEL" --show            # the closure this machine has now
bash "$SEL" --rollback        # put the previous closure back
```

The previous `/etc/pleb/session.env` is saved under
`/var/lib/plebian-os/closure-rollback.<timestamp>.*` with a record of the closure
that replaced it, so `--rollback` is available until the upgrade is committed and
afterwards. Keep `$SEL` until the upgrade has succeeded as an independent
recovery entrypoint, then `rm -f "$SEL"`.

Do not assemble pins from several releases or run a bare privileged provisioner
between closure selection and the updater. Back up irreplaceable personal data
even though preservation and rollback are release requirements.

### A local release tag can be stale, and `--offline` will trust it

The online path fetches the target tag with `--force`, so a tag that moved on the
remote is refreshed before use. **`--offline` does not.** It resolves
`refs/tags/v<x.y.z>` straight out of the local object store, so if that tag was
fetched earlier and has since moved — or was installed from a bundle — the
selector will validate and select the **old** closure without saying anything.
The version string matches, the selection succeeds, and the machine lands on
bytes nobody intended.

`v0.2.1` was force-moved during its release, so any checkout that fetched it
before the move holds a different commit under the same name.

Before selecting a closure on a machine that has seen this tag before, refresh
it explicitly:

```sh
git -C "$SRC" fetch --force origin 'refs/tags/v<x.y.z>:refs/tags/v<x.y.z>'
git -C "$SRC" rev-parse "v<x.y.z>^{commit}"   # compare with the published commit
```

If you are using `--offline` deliberately because the machine has no network,
verify that second command against the release's provenance record before
trusting the selection.

### Precondition: every source checkout must be clean

`plebian-os-update` refuses to start unless each source checkout it manages has
no local changes, and **untracked files count**:

```
[plebian-os] kilix checkout at <dir> has local changes; refusing a whole-stack
update whose rollback could overwrite them
```

One stray untracked file — an interrupted build, a debug file, a copied log — is
enough, with no tracked modification anywhere. The refusal is deliberate: the
update's rollback restores checkout positions, and it will not risk writing over
something it did not put there.

Check before selecting a closure, not after:

```sh
for d in "$HOME"/.local/gpu_terminal/sources/*/; do
    [ -d "$d/.git" ] || continue
    printf '%s %s\n' "$(git -C "$d" status --porcelain \
        --untracked-files=normal --ignore-submodules=none | wc -l)" "$d"
done
```

**Move such files out of the checkout; do not delete them.** They are yours, the
updater is refusing precisely so they survive, and deleting them to get the
upgrade moving throws away the thing being protected.

Note that this is the OS-layer whole-stack updater. It is a different mechanism
from `pleb update`, whose own handling of untracked files and development
worktrees is described in the release notes and does not apply here.
