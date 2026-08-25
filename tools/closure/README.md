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

## Requirements and checks

Use the release-pinned uv 0.12.5. From this directory:

```sh
uv run --locked python -m kilix_f120 contracts
uv run --locked python -m unittest discover -s tests -v
make check
```

The lock uses `jsonschema[format]==4.25.1` exactly. Qualified cache operation is
offline after the first immutable fetch: a validated hit performs no fetch.

## Command surface

```text
python -m kilix_f120 contracts
python -m kilix_f120 resolve REGISTRATION OUTPUT [--qualify]
    [--local-source INSTANCE=/absolute/path]
python -m kilix_f120 validate DOCUMENT [--allow-development-state]
python -m kilix_f120 stage REGISTRATION WORKSPACE_MANIFEST
    --cache CACHE --prefix PREFIX --release VERSION --release-lock LOCK
    [--report REPORT] [--local-source INSTANCE=/absolute/path]
python -m kilix_f120 reverse-deps DOCUMENT INSTANCE... [--direct]
python -m kilix_f120 evict --cache CACHE --namespace sources|builds --key SHA256
python -m kilix_f120 retire --prefix PREFIX [--release-lock LOCK]
```

`--local-source` is an explicit offline/evidence override. Its path is never
written into cache metadata or emitted in place of the registered canonical
HTTPS URL. Without an override, an observed checkout's `origin` must equal that
canonical URL.

`resolve` always writes an honest observed workspace manifest. Missing paths
become dirty/unresolved development records. `--qualify` additionally requires
the exact expected commit, a clean checkout, an allowed ref, verified committed
notice bytes, and the registered executable digests.

`stage` accepts only a manifest that already qualifies. It fetches each exact
commit into a content-addressed cache, builds each distinct frozen build key at
most once, audits every declared output, publishes a new prefix atomically, and
emits a validated release lock. Existing prefixes and locks are never
overwritten. Nested-source and recursive-submodule dependency modes block lock
emission until the corresponding consumer conversion actually lands.

`evict` moves one exact cache key to quarantine under its per-key lock. `retire`
moves one exact prefix (and optionally its lock) into a sibling private
retirement directory. Neither operation recursively targets a workspace or
cache root, and both remain recoverable for rollback inspection.

See `SEMANTICS.md` for the exact clarifications,
`SEMANTICS-REVIEW.md` for their freeze record, and `INTEGRATION.md` for the
registration/freeze procedure. Files under `fixtures/registrations/` are
development-only handoff scaffolds, not release facts.
