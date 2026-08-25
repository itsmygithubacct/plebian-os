# F120 external authority launcher

The files in this directory are source for the F120 trusted-launch boundary.
They are never executed in place for release evidence. A reviewed copy is
built into a new directory outside the subject, its runtime, and its dependency
source. The resulting `f120-authority` binary is the release entry point.

The native launcher opens the subject with `O_NOFOLLOW`, retains its directory
descriptor, verifies the complete file/type/mode/size/digest manifest, rejects
aliases, cross-device members, special files and reserved Python startup names,
and verifies the copied Python runtime, dependency closure and bootstrap before
Python starts. It then uses `execveat` on the retained interpreter descriptor
with the literal ordered flags `-I -S -B`, an empty external mode-0700 cwd and
an exact four-variable environment.

The bootstrap repeats the launch-envelope and closure checks. Only then does it
fork the frozen contract self-test and resolver tests, with the authority result
descriptor closed in each child. The native launcher accepts only one bounded,
canonical record on that descriptor; child stdout, a PASS string, and exit zero
cannot authorize the run.

## Construct a candidate bundle

Construction is not acceptance. Start with an exact clean export and an
external locked dependency directory. Invoke the builder with an already chosen
absolute interpreter and the resolved regular-file path of the compiler:

```sh
/absolute/python3.12 -I -S -B \
  /exact/export/tools/closure/authority/build_bundle.py \
  --subject /exact/export/tools/closure \
  --output /external/new/f120-authority-bundle \
  --interpreter /absolute/python3.12 \
  --dependency-root /external/site-packages \
  --cc /absolute/regular/compiler
```

The output path must not exist. The builder copies the minimal relocatable
runtime and dependency tree, writes canonical complete manifests, compiles the
PIE launcher, records source/compiler/runtime identities, writes
`BUNDLE-SHA256SUMS`, and removes all write bits. If construction fails, only the
new output directory is removed.

An independent acceptance step must verify the exact source ref, every line of
`BUNDLE-SHA256SUMS`, the build record, launcher identity and causal mutation
suite. The builder cannot approve its own output.

## Authority commands

Call the accepted external launcher directly for release and P9 evidence:

```sh
/external/accepted/f120-authority --subject /exact/export/tools/closure check
/external/accepted/f120-authority --subject /exact/export/tools/closure \
  cli contracts
```

All ordinary resolver subcommands follow `cli`. The terminal authority line is
`F120_AUTHORITY_ACCEPTED` plus a canonical record binding the run ID, subject
device/inode and subject-manifest digest. Any missing, extra, malformed or
identity-mismatched result is a refusal.

`make check` is retained only as a convenience delegator:

```sh
F120_AUTHORITY=/external/accepted/f120-authority make check
```

It refuses when the launcher is absent or non-absolute. The direct external
command above—not a subject Makefile—is the release authority entry point.

## Registered build commands

Registrations classify every tool as `native`, `script`, `python-interpreter`
or `python-script`. Scripts bind a named registered interpreter. Every exec in
the resulting process tree is stopped at the kernel exec event and matched to a
registered regular-file identity and digest. An undeclared child is killed
before its first user-space instruction.

Python scripts additionally require the exact authority interpreter and are
routed through this external bootstrap with `-I -S -B`, an empty external cwd,
the exact registered build environment, and retained source/script descriptors.
Direct Python commands are refused. Python tools needing third-party build
packages require a future explicit external dependency profile; ambient site
packages are never a fallback.
