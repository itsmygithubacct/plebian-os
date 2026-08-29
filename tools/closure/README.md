# Kilix F120 closure tooling

This directory implements the frozen `kilix.f120.workspace-manifest/v1` and
`kilix.f120.release-lock/v1` formats, an exact source/build cache, deterministic
reverse-dependency queries, and atomic staged-provider prefixes.

F120 owns a format, never a truth. Its documents are unauthenticated build
evidence. They may support a refuse-only integrity check, but they never select
a release, grant trust, replace an owning contract, create a repository, move a
pin, publish an artifact, or authorize a migration.

The byte-frozen contract package is vendored in `contracts/`. Its schemas,
validator, fixtures, lock and review record are protected by the package's
`SHA256SUMS`; the adapter additionally pins that hash manifest's digest. The
single owner-named qualification exception is preserved exactly:
`component_id=plebian-os`, `ref_kind=tag`, `requested_ref=v0.2.0`. No other
mutable ref qualifies.

## Trusted launch and checks

Release and P9 evidence must use an independently accepted external authority
bundle built as documented in `authority/README.md`. The old subject-cwd
`uv run ... python` commands are deliberately no longer qualifying commands.
From an exact export:

```sh
/external/accepted/f120-authority \
  --subject /exact/export/tools/closure check
F120_AUTHORITY=/external/accepted/f120-authority make check
```

The direct external command is the authority entry point; the Make target is a
convenience delegator and refuses without an absolute launcher. The bundle pins
Python 3.12.8, the bootstrap and a copied dependency closure containing
`jsonschema[format]==4.25.1`. It verifies the complete subject before loading
the validator and accepts only its dedicated canonical result record.

Qualified cache operation is offline after the first immutable fetch: a
validated hit performs no fetch. Publication requires Linux
`renameat2(RENAME_NOREPLACE)` and fails closed when the kernel/libc surface is
unavailable.

## Command surface

```text
f120-authority --subject SUBJECT cli contracts
f120-authority --subject SUBJECT cli assemble OUTPUT --workspace-root ROOT
    --report REPORT --required-owner OWNER... --fragment OWNER=/absolute/path...
f120-authority --subject SUBJECT cli resolve REGISTRATION OUTPUT [--qualify]
    [--local-source INSTANCE=/absolute/path]
f120-authority --subject SUBJECT cli validate DOCUMENT [--allow-development-state]
f120-authority --subject SUBJECT cli stage REGISTRATION WORKSPACE_MANIFEST
    --cache CACHE --prefix PREFIX --release VERSION --release-lock LOCK
    [--report REPORT] [--evidence-report EVIDENCE]
    [--local-source INSTANCE=/absolute/path]
f120-authority --subject SUBJECT cli stage-matrix REGISTRATION WORKSPACE_MANIFEST
    --output NEW_DIRECTORY --release VERSION
    [--local-source INSTANCE=/absolute/path]
f120-authority --subject SUBJECT cli reverse-deps DOCUMENT INSTANCE... [--direct]
f120-authority --subject SUBJECT cli evict --cache CACHE --namespace sources|builds --key SHA256
f120-authority --subject SUBJECT cli retire --prefix PREFIX [--release-lock LOCK]
```

`--local-source` is an explicit offline/evidence override. Its path is never
written into cache metadata or emitted in place of the registered canonical
HTTPS URL. Without an override, an observed checkout's `origin` must equal that
canonical URL.

`resolve` always writes an honest observed workspace manifest. Missing paths
become dirty/unresolved development records. `--qualify` additionally requires
the exact expected commit, a clean checkout, an allowed ref, verified committed
notice bytes, and the registered executable digests.

`assemble` consumes an explicit named set of reviewed owner fragments and
refuses a missing, unexpected or duplicate owner. It sorts the union,
preflights final commits, tools, builds, licences, notices, edges, artifact
names/paths and staged-dependency recipe tokens, and atomically publishes a new
registration and its digest-bound assembly report as new files. The report is
published first, so an interruption cannot expose an assembled registration
without its receipt; a normal output refusal cleans the new report. Existing
output/report files are never overwritten. The command cannot manufacture owner
facts: F106, F110 and F111 owners still supply the exact fragments and receipts.

`stage` accepts only a manifest that already qualifies. It fetches each exact
commit into a content-addressed cache, builds each distinct frozen build key at
most once, audits every declared output, publishes a new prefix atomically, and
emits a validated release lock. Existing prefixes and locks are never
overwritten. Nested-source and recursive-submodule dependency modes block lock
emission until the corresponding consumer conversion actually lands. Cache and
prefix paths must be outside the registered workspace and disjoint from each
other. The default `kilix.f120.stage-report/v1` remains byte-shape compatible.
The opt-in `kilix.f120.stage-evidence-report/v1` includes one exact source and
build receipt per component, the provider-first build order and retained
Git-object `fetch_bytes`; a warm hit records zero fetches, zero fetch bytes and
zero builds for every component. Its path must be new, outside the workspace,
cache and staged prefix, and distinct from the inputs, lock and summary report.
An evidence-publication failure recoverably retires the newly published prefix
and lock.

`stage-matrix` performs the required cold, warm and independent-clean legs as
one new-directory transaction. The cold and warm legs share exactly one new
cache; the independent leg uses a second new cache. It requires exactly one
miss/fetch for every distinct cold and independent source key, exactly one
miss/build for every distinct build key, and zero misses, fetches, fetch bytes
or builds in the warm leg. It emits the 3/3 stage summaries, detailed receipts,
validated locks and no-follow prefix inventories, then refuses unless all 3/3
locks and all 3/3 inventories are byte-identical. The final report binds the
captured registration/workspace hashes, common lock and inventory hashes,
provider-first order and exact key populations. Success publishes the complete
directory with an atomic no-replace rename. A failed candidate is moved to a
private sibling retirement directory for inspection; an existing or racing
output is never replaced. P9 uses no `--local-source` overrides.

The P9-H2 candidate adds a deterministic `staged-prefix` build graph. Providers
build before consumers; a consumer names each direct provider only through
`{dependency:INSTANCE_ID}`. Its key binds a canonical vector of the provider's
instance, build key and artifact identities through the reserved
`build_options.f120_staged_dependencies_sha256` scalar. This changed companion
surface is construction-only until the independent review and refreeze stated
in `P9-STAGED-DEPENDENCY-SEMANTICS.md`; it does not change frozen contract
bytes or authorize a consumer migration.

Every registered executable is classified as `native`, `script`,
`python-interpreter` or `python-script`; scripts bind a named registered
interpreter. Linux ptrace exec events bind every executable descendant before
its first user-space instruction. Undeclared children are refused. Registered
Python scripts run only through the external pinned interpreter/bootstrap with
`-I -S -B`; direct or ambient Python selection is refused.

`evict` moves one exact cache key to quarantine under its per-key lock. `retire`
moves one exact prefix (and optionally its lock) into a sibling private
retirement directory after verifying F120 stage markers and, when supplied,
exact lock-to-file agreement. Neither operation recursively targets a workspace
or cache root, and both remain recoverable for rollback inspection.

See `SEMANTICS.md` for the exact clarifications,
`SEMANTICS-REVIEW.md` for their freeze record, and `INTEGRATION.md` for the
registration/freeze procedure. The unaccepted P9-H2 successor semantics are in
`P9-STAGED-DEPENDENCY-SEMANTICS.md`. Files under
`fixtures/registrations/` are development-only handoff scaffolds, not release
facts.
