# F120 v1 companion semantics

**Companion identity:** `kilix.f120.companion-semantics/v2`

**Status:** refrozen clarification alongside byte-frozen workspace/release v1;
this file does not alter an accepted schema or fixture.
`contracts/SHA256SUMS` must remain unchanged. Registration inputs use
`kilix.f120.registration/v2`; v1 registration is refused because it cannot bind
the executable classification/interpreter closure added by this revision.

## Authority boundary

F120 records values supplied or observed under an owning stream's contract. A
workspace manifest and release lock are unauthenticated evidence and can only
refuse on disagreement. They never grant authority, choose a release, authorize
a repository or migration, or replace F100/F106/F110/other owner truth.

## Canonical representation

Canonical JSON is UTF-8 `json.dumps(value, indent=2, sort_keys=True)` plus one
LF, with non-finite numbers forbidden. Duplicate keys and documents over 4 MiB
are rejected. Arrays whose ordering is semantic (`features`, tests, licences by
SPDX, notices by path, component instances, dependency edges and artifacts) are
sorted and unique before publication.

## Identity and source bytes

`instance_id` distinguishes path-addressed occurrences. If an owner does not
supply one, it is:

```text
component_id + "-" + sha256(normalized_relative_path_utf8)[0:12]
```

`source_sha256` identifies the committed Git tree, not a tar encoding, checkout
metadata, dirty bytes, or submodule checkout contents. Start SHA-256 with the
domain bytes `kilix.f120.source-tree/v1\0`. Walk `git ls-tree -r -z --full-tree
COMMIT` order. For each entry, length-prefix with an unsigned eight-byte
big-endian count and hash, in order: mode, object kind, object ID, raw path, and
blob bytes. A gitlink hashes its commit identity and an empty content field; it
is not recursively traversed. Finish with the entry count as unsigned
eight-byte big-endian. Unsupported object kinds fail closed.

A resolved manifest records the observed checkout `HEAD`. Dirty and untracked
bytes set `dirty=true` but never change `source_sha256`. Notice hashes are
verified against blobs committed at that same `HEAD`.

Canonical source URLs are credential-free HTTPS URLs with lowercase host, no
query or fragment, and no trailing slash. A noncanonical observed remote is a
drift error unless the operator supplied an explicit local evidence override.

Qualification requires exact-commit refs with `requested_ref == expected_commit
== resolved_commit`, except for the one fixed baseline record:

```text
component_id = plebian-os
ref_kind = tag
requested_ref = v0.2.0
```

The tag must still resolve to `expected_commit`, checkout `HEAD` must match it,
and the checkout must be clean. No other tag or branch qualifies.

## Toolchain, options, features and tests

Every build executable is registered by logical name, absolute path, SHA-256,
kind and optional interpreter name and verified immediately before either a
cache hit or build. Paths are local execution inputs and are excluded from
persistent metadata. The toolchain digest is SHA-256 of canonical JSON:

```json
{
  "executables": [
    {"interpreter": null, "kind": "native", "name": "cc", "sha256": "..."}
  ],
  "name": "gnu-c",
  "version": "14.2.0"
}
```

Executable entries are sorted and unique by name. Kinds are `native`, `script`,
`python-interpreter` and `python-script`; both script kinds bind a registered
interpreter. `version` is an owner-pinned identity string, not runtime discovery.
A build's `PATH` is a private directory containing only logical-name symlinks to
those digest-verified executables; it never inherits `/usr/bin`, `/bin` or an
operator path. A Linux ptrace monitor stops every descendant at its kernel exec
event and refuses an identity absent from the registration before its first
user-space instruction. This makes registration of executable children an
enforced closure rather than owner prose.

`features` are sorted, owner-declared output-affecting capabilities.
`build_options` are canonical scalar output-affecting inputs; NaN and infinity
are forbidden. `required_tests` are sorted gate identifiers and are evidence
requirements, not commands the resolver invents or silently runs.

The registration's complete declared recipe (commands, environment, copies and
artifacts) has its own canonical digest. It is injected as the reserved
`build_options.f120_recipe_sha256`, ensuring a recipe change changes the frozen
build key without defining a parallel key.

The only build-cache key is the frozen validator derivation:

```text
sha256(canonical({
  architecture,
  build_options,
  features,
  source_sha256,
  toolchain_digest
}))
```

`SOURCE_DATE_EPOCH` is the literal `0`. A commit timestamp is not a build input:
`resolved_commit` is release evidence, while the frozen key deliberately binds
the exact committed tree through `source_sha256`. Consequently two commits with
the same source tree share one source entry and one build entry, and a forced
rebuild from either commit produces the same staged bytes.

## Dependency vocabulary

Inventory observations map as follows:

- a recursively initialized Git dependency: `recursive-git-submodule`;
- a provider compiled from a nested/sibling source tree: `nested-source-build`;
- an immutable F120 public prefix: `staged-prefix`;
- a distribution/host package surface: `system-package`;
- an independently running IPC/CLI service: `runtime-process`.

Declaration-only inventory sightings do not create an edge by themselves.
Qualified release-lock emission rejects recursive/nested build modes: the mode
may change to `staged-prefix` only after the consumer conversion lands and its
tests and rollback have been demonstrated.

## Cache and staged prefix

Source entries live at `sources/sha256/SOURCE_DIGEST`; build entries at
`builds/sha256/BUILD_KEY`. A per-key `flock` serializes writers. Candidates are
verified before same-filesystem Linux `renameat2(RENAME_NOREPLACE)` publication;
the operation fails closed if true atomic no-replace rename is unavailable.
Every hit revalidates its metadata and bytes. A corrupt entry is atomically
moved under `quarantine/` and recreated; it is never silently used. Metadata
contains content identities, not credentials, operator paths, hostnames,
commits or timestamps. The source entry
retains one exact tree behind `refs/kilix-f120/source`; its commit identity does
not alter the content key. A cold report records the exact received Git object
bytes retained as a pack (or, if Git unpacks it, the exact compressed loose-
object bytes); a hit records zero.

Build commands do not use a shell and must start with a registered
`{tool:name}`. They run under a bounded, minimal environment with fixed locale,
timezone, source epoch and temporary directory. Registered environment input
cannot replace `HOME`, `PATH`, Git credential controls, reproducibility
variables, Python startup state, loader state, virtual environments or
package-manager/plugin configuration. Direct Python-interpreter commands are
refused. A `python-script` is invoked with the authority bundle's exact pinned
interpreter and external bootstrap under `-I -S -B`; its initial cwd is an empty
mode-0700 directory and the source is added only after that envelope is checked.
Recipe-controlled names are confined to `F120_INPUT_[A-Z0-9_]+`, making this a
positive namespace rather than a finite startup-variable denylist. Cancellation
kills the build process group.

A cached build prefix contains exactly its declared regular files—no symlinks,
devices or undeclared/private outputs. Artifact bytes are refused if they embed
the workspace, cache, work, prefix or operator-home path. A staged workspace is
published only with the same atomic no-replace primitive to a new path outside
both the workspace and cache and adds one canonical
`share/kilix-f120/INSTANCE.json` manifest per component. Release artifacts bind
source, frozen build key, architecture, toolchain, features and canonical
licence-array digest exactly as the frozen validator derives them. The lock is
published with no-replace semantics; if its paired publication fails after the
prefix rename, the prefix is recoverably moved out of its public name. Retirement
refuses arbitrary directories and repositories and accepts only a marked F120
stage whose optional lock validates and exactly binds every staged file.
