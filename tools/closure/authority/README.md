# Shared trusted-launcher source

These files implement one external trusted-launch boundary. They are never
executed in place for release evidence. A reviewed copy is built into a new
directory outside the subject, runtime and dependency source; the profile
chooses the resulting launcher's basename and its exact command/child table.

Construction is not acceptance. The builder of launcher or profile bytes is
not eligible to review them, and a consumer may not adopt changed bytes until
an independent cross-family review accepts their exact identities.

## Fixed boundary

The native launcher opens the subject with `O_NOFOLLOW`, retains its directory
descriptor, verifies the complete file/type/mode/size/digest manifest, rejects
aliases, cross-device members, special files and reserved Python startup names,
and verifies the copied Python runtime, dependency closure, bootstrap and
canonical profile before Python starts. It then uses `execveat` on the retained
interpreter descriptor with literal ordered `-I -S -B`, an empty external
mode-0700 cwd and an exact four-variable environment.

The bootstrap independently rechecks the envelope, three closure manifests and
profile digest. It recomputes the terminal-check-set digest from the selected
command's ordered child IDs, executes every child through the same retained
interpreter/bootstrap boundary, and rechecks all three closures after every
child. The result descriptor is closed in children. The native launcher accepts
only one bounded canonical result on that descriptor; child stdout, familiar
PASS text and exit zero cannot authorize a run.

## Profile contract

`kilix.trusted-launcher.profile/v1` is canonical, duplicate-free UTF-8 JSON:
sorted keys, compact separators and exactly one final LF. Unknown members,
absolute paths, `..`, interior dot segments, duplicate commands/children/paths,
unbounded tables and unsupported child kinds are refused during construction.
The same profile bytes are copied to `launch-profile.json`, hashed into the
native executable, opened without following symlinks, and reparsed from the
retained descriptor by the bootstrap.

A profile supplies:

- a `profile_id` and launcher basename;
- one or more named commands, each with forbidden or required forwarded argv;
- an ordered, nonempty child table for each command;
- optional exact subject hash manifests checked before children; and
- per-child Python import roots and case/result expectations.

The closed child kinds are `python-script`, `python-module` and
`python-unittest`. Script and module cases bind fixed argv, an expected exit
status, and an exact stdout/stderr policy: empty, literal UTF-8, a file in the
retained subject/dependency closure, or bounded passthrough. Argument path
objects name only retained `subject`, `dependency`, `runtime`, `launcher`,
`python` or `temporary` roots. No shell, PATH-selected interpreter, env shebang,
consumer wrapper or arbitrary environment extension is part of the interface.

The terminal-check-set bytes are every child ID in order, each followed by LF.
The builder hashes those bytes into the native command table; the bootstrap
re-derives the same digest from `launch-profile.json` before running a child.

## Supplied profiles

- `profiles/f120-reference-v1.json` preserves F120's `check` and `cli`
  surfaces while moving all hard-coded children into data.
- `profiles/track-d-td-p1-v1.json` encodes TD-P1's external candidate validator,
  bound-interpreter hardware replay and bound-interpreter model-sizer replay.
  Its two replay children compare all 7/7 F107-B argv/fixture pairs byte for
  byte. It does not freeze or accept the P1 candidate.
- `profiles/track-d-td-hw-v1.json` encodes the hardware unittest leg, three
  staged `plebian-hardware` console invocations and exact invalid-argv refusal.
  Staged children expose only the dependency-stage site-packages root, so the
  production console cannot fall back to source. Launcher acceptance proves
  execution integrity only; live hardware remains
  `qualification_eligible=false` pending its separate coverage rows.

Track D must build its final stage so `dependencies/bin/plebian-hardware`,
`dependencies/bin/uv` and `dependencies/lib/python3.12/site-packages` are exact
members of the copied dependency closure. Any product, stage, process-graph or
profile change requires the applicable fresh consumer campaign.

## Construct a candidate bundle

Start with an exact independent export and an external locked dependency tree.
Invoke the builder with an already chosen absolute interpreter, regular-file
compiler and canonical profile:

```sh
/absolute/python3.12 -I -S -B \
  /exact/export/tools/closure/authority/build_bundle.py \
  --subject /exact/export/tools/closure \
  --profile /exact/export/tools/closure/authority/profiles/f120-reference-v1.json \
  --output /external/new/f120-authority-bundle \
  --interpreter /absolute/python3.12 \
  --dependency-root /external/site-packages \
  --cc /absolute/regular/compiler
```

Omitting `--profile` selects the F120 reference profile for compatibility. The
output path must not exist. The builder copies the minimal relocatable runtime
and dependency tree, writes canonical complete manifests, compiles the PIE
launcher, records source/compiler/runtime/profile identities, writes
`BUNDLE-SHA256SUMS`, and removes all write bits. Failure removes only the exact
new output directory.

An independent acceptance step must verify the exact source ref, every line of
`BUNDLE-SHA256SUMS`, build record, launcher/profile identities, complete common
mutation matrix and the selected family's consumer campaign.

## F120 commands

The reference profile retains the direct external commands:

```sh
/external/accepted/f120-authority --subject /exact/export/tools/closure check
/external/accepted/f120-authority --subject /exact/export/tools/closure cli contracts
```

`make check` is only a convenience delegator. The direct external launcher—not
a subject Makefile—is the release authority entry point.

F120 registrations still classify every tool as `native`, `script`,
`python-interpreter` or `python-script`. Registered Python scripts use the
generic retained launcher descriptors; the provider's F120 input namespace and
execution-closure rules remain F120's consumer contract, not profile syntax.
