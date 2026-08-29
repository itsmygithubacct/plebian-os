# F120 P9 staged-dependency companion candidate

**Candidate identity:** `kilix.f120.staged-dependencies/v1`

**Status:** Track H construction candidate for P9-H2. It is not accepted,
refrozen or P9-usable until two independent exact-byte passes accept it and an
accepted companion-semantics successor binds these bytes. It changes no byte
under `contracts/` and does not reinterpret the frozen workspace-manifest/v1
or release-lock/v1 validators.

## Graph and build order

Only `staged-prefix` edges affect build order. For an edge whose `from` is the
consumer and `to` is the provider, the provider is built first. Ready nodes are
selected in instance-ID order, so registration component order cannot alter a
build. Unknown endpoints, duplicate direct edges, self-edges and cycles refuse
before a release prefix or lock is published. Other consumption modes expose no
build prefix.

Each consumer must reference every direct staged dependency, and no other
dependency, with the exact recipe token:

```text
{dependency:INSTANCE_ID}
```

The token expands to a per-build copy containing exactly the provider cache
entry's declared regular files. Its files and directories have all write bits
removed. The complete view is checked against the provider's cache metadata
before and after the consumer command. Dependency views are separate by
instance ID; they are never merged with a host, workspace or sibling-source
path.

Every recipe argument or environment value containing a path must bind it
through `{source}`, `{build}`, `{prefix}`, `{tool:NAME}` or a declared
`{dependency:INSTANCE_ID}`. Literal absolute paths, parent segments, path-like
values without a token and undeclared dependency tokens refuse. The exact
committed source and registered executable closure remain inputs; this
interface does not claim to be a general-purpose filesystem sandbox.

## Derived dependency binding

For each direct staged dependency, read its verified build metadata and emit
one record per artifact with exactly these fields:

```json
{
  "artifact_id": "provider-header",
  "artifact_sha256": "...",
  "build_key_sha256": "...",
  "component_instance": "provider",
  "path": "include/provider.h"
}
```

Sort the records by component instance, build key, artifact ID, path and
artifact SHA-256. The consumer dependency digest is:

```text
sha256(canonical({
  "dependencies": RECORDS,
  "schema": "kilix.f120.staged-dependencies/v1"
}))
```

The stage operation adds that digest as the reserved scalar
`build_options.f120_staged_dependencies_sha256` in its derived consumer
component. Registrations may not supply either this field or the existing
`f120_recipe_sha256` field. The qualified input workspace remains unchanged;
the derived component is used for the build cache and release-lock projection.
The frozen build-key formula therefore binds the dependency vector without a
second key algorithm, and the frozen release validator checks every consumer
artifact against the same projected build options.

A transitive provider change propagates because each direct record includes
the provider build key. Changing any provider instance, build key, artifact ID,
path or artifact digest changes the direct consumer key and recursively changes
its dependants' vectors.

## Publication and consumers

Artifact IDs and final staged paths are unique across the complete closure.
Even byte-identical duplicate final paths refuse. Build and source cache hits
are fully revalidated, and a consumer cannot publish if a dependency view or
cache entry changes during its build.

F106, F110 and F111 owners remain responsible for landing their actual consumer
conversion: the recipe token, linkage/import choice, installed-surface tests,
private-API disposition and walked rollback. Track H supplies one shared
mechanism and does not edit consumer worktrees or invent final registration
facts. An edge may be changed to `staged-prefix` only after that owner evidence
lands.

## Required acceptance evidence

The focused causal population must include all 7/7 conditions:

1. a consumer listed before its provider still builds after the provider;
2. cold execution fetches 2/2 sources and builds 2/2 components;
3. one provider artifact change fetches 1/2 sources and rebuilds 2/2
   components;
4. the warm replay fetches 0/2 sources and builds 0/2 components;
5. an independent empty cache fetches 2/2 and builds 2/2;
6. warm and independent locks and prefixes are byte-identical to the changed
   cold leg; and
7. undeclared, missing, host-path, collision, corruption and cycle controls
   refuse without a public prefix or lock.

The complete frozen-contract, source-cache, build-cache, concurrency,
corruption, cancellation, publication-race and retirement populations must
also pass. Review must verify the exact commit/tree/path hashes and state every
assessed and unassessed population with denominators. No builder-authored pass
or earlier F120/launcher review transfers to these bytes.
