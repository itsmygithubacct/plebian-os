# F120 P9 staged-dependency companion candidate

**Candidate identity:** `kilix.f120.staged-dependencies/v1`

**Status:** Track H R6 construction successor for P9-H2/P9-H1 mechanics. It is not accepted,
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

## Owner-fragment assembly and cache receipts

The `assemble` surface takes 2/2 independent lists: required owner IDs and
`OWNER=/absolute/path` fragments. The sets must match exactly. It captures each
regular non-symlink fragment without a changing-byte race, validates it as
registration/v2, sorts components and edges independently of argument order,
and binds every fragment SHA-256 in
`kilix.f120.registration-assembly-report/v1`.

Release preflight refuses all 8/8 unresolved or ambiguous populations: zero
commits/digests, non-exact refs, missing recipes/tools, `NOASSERTION`, duplicate
components/edges/artifacts/paths, missing/self endpoints, API/ABI disagreement
and staged-prefix cycles or recipe-token disagreement. Output and report use
atomic new-file publication and never overwrite an existing byte. This is a
mechanical landing surface; only F106/F110/F111 owners can supply or review
their facts.

`landings` closes the mechanical gap between those owner facts and the
assembled graph. The required-owner set and receipt-owner set must match
exactly. The assembly report must bind the captured registration and map every
component to exactly one required owner. Every `staged-prefix` edge then has
exactly one landing filed by its consumer's mapped owner; non-staged edges have
zero landing records. An owner with zero such edges still supplies one receipt
with an empty array.

The same receipt has exactly one component-test record for every component
mapped to that owner. Its test IDs and order must equal the component's
complete canonical `required_tests` list. Every component test binds non-empty
argv, the component's exact registered commit, integer-zero exit and retained
evidence. Thus an edge-free owner has 0 edge landings but still supplies N/N
component receipts; neither test population can substitute for the other.

Each edge landing binds the exact registered endpoint commits, runtime-process
identity and `{dependency:PROVIDER}` token. Its installed-surface test IDs must
equal the edge's complete canonical `required_tests` list. Linkage/import,
every installed-surface test, private-API disposition and rollback each bind a
nonzero SHA-256 evidence reference and the exact consumer commit; test and
rollback exits must be integer zero. `not-used` and `removed` are the only
closed private-API states. Referenced evidence IDs and explicitly supplied
regular non-symlink files form equal sets, and observed evidence hashes must
match. The output report omits local paths and command text, publishes only as
a new file and cannot accept the technical sufficiency of the owner evidence.
That judgment remains outside this construction candidate.

Before execution, `landing-template` may project the exact owner/component/edge
population from the captured registration and assembly report. The output is a
separate non-evidence template set: registered commits, recipe tokens and test
IDs are filled, but every command, exit, evidence digest, linkage selection and
private-API disposition remains null. An unfilled projection is deliberately
not a consumer return and cannot satisfy `landings`.

`kilix.f120.stage-evidence-report/v1` retains 2/2 exact per-component vectors
without changing the default `kilix.f120.stage-report/v1` shape. Source
receipts bind instance, canonical URL, resolved commit, committed-tree/cache
key, local-override state, hit/miss, fetch count and bytes. Build receipts bind
instance, build key, staged-dependency digest, artifact count, hit/miss and
build count. The report also records the actual provider-first build order.
The accepted tree-level source-cache and frozen build-key derivations are
unchanged.

## Retained three-leg proof transaction

`stage-matrix` turns the required cold, warm and independent-clean exercise
into one atomic retained result. Its output must be a new absolute directory
outside the workspace. The command creates 2/2 new caches: cold and warm share
1/2, while independent-clean uses the other 1/2. P9 supplies 0 local-source
overrides.

For both 2/2 initially empty caches, every distinct source-tree key must miss
and fetch exactly 1/1 times and every distinct build key must miss and build
exactly 1/1 times. Multiple component instances sharing a committed tree reuse
that one source object; their denominated component receipts remain separate.
The warm leg requires 0 source misses, 0 fetches, 0 fetch bytes, 0 build misses
and 0 builds across its complete receipt populations. Cold and
independent-clean detailed evidence must be byte-identical.

Each 3/3 prefix is inventoried from retained no-follow descriptors. The
inventory records every directory and regular file's normalized relative path
and mode, plus every regular file's byte length and SHA-256; a symlink, special
entry or changing inode refuses. The 3/3 validated locks must be byte-identical
and the 3/3 canonical prefix inventories must be byte-identical before the
matrix report is published.

The `kilix.f120.stage-matrix-report/v1` result binds the captured registration
and workspace-manifest SHA-256 values, release, common lock length/digest,
common prefix-inventory digest, component/artifact populations, unique source
and build key populations, provider-first order and the 3/3 per-leg
report/evidence/lock/inventory digests. The complete candidate directory is
published through an atomic no-replace rename. A failure moves only that
candidate into a private sibling retirement directory; an existing or racing
output is preserved byte-for-byte.

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
also pass. Assembly review must cover all 6/6 mutation families: argument-order
equality, missing/extra/duplicate owner, unresolved field, duplicate/unknown
graph identity, API/ABI or recipe mismatch, and existing-output refusal with
no partial pair. Report review must prove all 2/2 receipt vectors are complete
for cold, warm and independent-clean legs. Matrix review must additionally
cover all 6/6 new test populations: exact 3/3-leg CLI output, shared-tree
fetch-once with a staged consumer, existing/dangling output refusal, no-follow
prefix inventory, recoverable failed-candidate retirement and competing-writer
publication. Review must verify the exact commit/tree/path hashes and state every
assessed and unassessed population with denominators. No builder-authored pass
or earlier F120/launcher review transfers to these bytes.
