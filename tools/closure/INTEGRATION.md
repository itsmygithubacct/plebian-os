# Registering a component with F120

Registration is an implementation input, not a third frozen contract and not
release authority. Copy the closest file under `fixtures/registrations/`, then
replace every sentinel using the owning stream's reviewed values.

## S120 handoff

Dependent streams consume the exact published Track H commit announced in the
release coordination log, never an unrecorded moving branch head. Build and
independently accept the external authority bundle described in
`authority/README.md` from that exact tree. The qualifying command is the
external process, not a wrapper stored in the tree:

```sh
/external/accepted/f120-authority \
  --subject /exact/export/tools/closure check
```

For developer ergonomics, the exact accepted launcher can also be passed as
`F120_AUTHORITY` to `make --no-print-directory -C tools/closure check`; that
subject Makefile is not the release authority. The launcher verifies the frozen
v1 bytes and complete subject before running their validator, the companion
semantics, the resolver/cache/staging suite and all ten pre-repository component
scaffolds. A passing handoff gate proves the interface is available; it does not
turn a scaffold into authority or make a development manifest a qualified
release closure.

The stable consumer surface is the command set documented in `README.md`, this
registration procedure, staged headers/libraries/commands beneath one prefix,
and exact F120 workspace/release document schemas. Incompatible changes require
a new interface/schema identity rather than an in-place reinterpretation.

## Before a repository exists

Keep the checkout path absent and record:

- `expected_commit` and an exact `requested_ref` as forty zeroes;
- `visibility=local-only` and `publication_disposition=unpublished` unless an
  owner has already decided otherwise;
- placeholder version/architecture/licence/notice/tool values clearly marked
  by the scaffold;
- the intended credential-free canonical HTTPS URL and component-relative
  path.

Running `resolve` without `--qualify` emits a schema-valid, dirty/unresolved
workspace record. That demonstrates format conformance while making it
impossible to mistake the scaffold for qualified release evidence.

## Qualification procedure

1. Land the owning repository/component and its public install surface.
2. Replace sentinels with the reviewed canonical URL, exact 40-hex commit,
   component/API/ABI versions, architecture, features, tests, visibility,
   publication disposition, licences and committed notice hashes.
3. Register every build executable, including executable children, with its
   absolute local path, exact file SHA-256 and `kind`: `native`, `script`,
   `python-interpreter` or `python-script`. Each script also names its registered
   `interpreter`; a Python script's interpreter must be the exact release-pinned
   authority Python. Pin a human-readable toolchain version string. Sort tools
   by name. The build receives only these logical tool names on `PATH`, and the
   execution monitor refuses every undeclared exec descendant.
4. Declare no shell command. Each command begins with `{tool:name}` and uses
   only argv placeholders `{source}`, `{build}`, `{prefix}`, `{tool:name}` and,
   for a direct `staged-prefix` edge only, `{dependency:INSTANCE_ID}`. Every
   direct staged dependency must be referenced and every referenced dependency
   must have that edge. Literal absolute, parent, host and sibling-source paths
   are refused.
   Recipe environment names, when unavoidable, must use the
   `F120_INPUT_[A-Z0-9_]+` namespace; every other recipe-controlled environment
   name is refused so a new plugin/package-manager startup variable cannot
   bypass a finite denylist.
5. Declare exact source-to-prefix copies and one artifact entry for every
   destination. Lists are sorted; artifact IDs must be unique across the whole
   closure. Private headers and sources are never staged.
6. Record dependency edges and their actual consumption modes. Versions on an
   edge must equal the target's declared API/ABI versions.
7. Run `resolve ... --qualify`; investigate every refusal rather than weakening
   a field or using a mutable ref.
8. For each `staged-prefix` consumer, land the owning component's linkage or
   import choice, installed-surface tests, private-API disposition and walked
   rollback before changing the edge. Track H supplies the shared dependency
   token and derived key binding; it does not perform that consumer change.
9. Run the 3/3-leg proof as one retained transaction:

   ```sh
   /external/accepted/f120-authority --subject /exact/export/tools/closure cli \
     stage-matrix /private/p9/registration.json \
     /private/p9/workspace-manifest.json \
     --output /private/p9/new-stage-matrix --release 0.2.1
   ```

   The output directory must not exist. The command creates 2/2 new caches,
   runs cold and warm against the shared cache and independent-clean against
   the other, and emits 3/3 summaries, detailed receipt sets, locks and
   no-follow prefix inventories. The warm leg must report 0 misses, 0 fetches,
   0 `fetch_bytes` and 0 builds across its complete populations. All 3/3 locks
   and 3/3 prefix inventories must be byte-identical. P9 supplies 0 local-source
   overrides; the option exists only for development evidence.

## Exact owner-fragment assembly

P9 names every expected owner independently of the fragments supplied. Use an
explicit absolute path for each reviewed return; do not use a glob:

```sh
/external/accepted/f120-authority --subject /exact/export/tools/closure cli \
  assemble /private/p9/registration.json \
  --workspace-root /private/p9/workspace \
  --report /private/p9/registration-assembly-report.json \
  --required-owner f106 --fragment f106=/reviewed/f106.json \
  --required-owner f110 --fragment f110=/reviewed/f110.json
```

The 2/2 names above are the complete 0.2.1 release owner population after
OD-28c deferred F111 and its F120 consumer requirement to 0.2.2. F111 must not
be supplied or expected in a 0.2.1 P9 run. These names are release coordination
identities, not inferred product truth. The output is order-independent and
refuses a missing/extra owner, duplicate component or edge, unknown endpoint,
unresolved final field,
API/ABI mismatch, artifact collision, staged cycle, or recipe/edge mismatch.
The report binds every fragment digest, the exact component set, provider-first
build order and assembled registration digest. It is private evidence and does
not accept a fragment or authorize a consumer conversion.

## Exact consumer-landing evidence

After the 2/2 owner fragments are assembled, name those same 2/2 owners again
and supply one receipt file per owner. Also supply every evidence ID referenced
by those receipts through a separate explicit list; use no glob:

```sh
/external/accepted/f120-authority --subject /exact/export/tools/closure cli \
  landing-template /private/p9/registration.json \
  /private/p9/registration-assembly-report.json \
  --output /private/p9/consumer-landing-templates.json \
  --required-owner f106 --required-owner f110
```

This optional projection binds the registration and assembly digests and lists
every required component test and staged edge for its mapped owner. Its null
fields must be replaced only from retained owner evidence; the template itself
is not a receipt and is refused by `landings`. Each owner extracts its matching
`templates[].receipt` object as a standalone file, fills every null from the
retained execution, and returns that file with its exact evidence-slot files.

```sh
/external/accepted/f120-authority --subject /exact/export/tools/closure cli \
  landings /private/p9/registration.json \
  /private/p9/registration-assembly-report.json \
  --output /private/p9/consumer-landing-report.json \
  --required-owner f106 --receipt f106=/reviewed/f106-landings.json \
  --required-owner f110 --receipt f110=/reviewed/f110-landings.json \
  --evidence f106-component-tests=/retained/f106-component-tests.txt \
  --evidence f110-component-tests=/retained/f110-component-tests.txt \
  --evidence f110-telemetry-link=/retained/f110-telemetry-link.txt \
  --evidence f110-telemetry-installed=/retained/f110-telemetry-installed.txt \
  --evidence f110-telemetry-private=/retained/f110-telemetry-private.txt \
  --evidence f110-telemetry-rollback=/retained/f110-telemetry-rollback.txt
```

The evidence names are illustrative; the owners return the actual exact set.
Every owner receipt has schema `kilix.f120.consumer-landing/v1`, binds the
registration and assembly-report SHA-256 values, and carries a canonically
ordered `component_tests` array plus a canonically ordered `landings` array.
`component_tests` contains exactly one record for every component mapped to
that owner and one passing command/commit/evidence receipt for every canonical
component `required_tests` ID. Owners with 0 staged edges return an empty
`landings` array, rather than disappearing from the owner population or
omitting their component tests. Each edge landing contains:

- consumer/provider instance IDs and their exact registered commits;
- `runtime_process` and the exact `{dependency:PROVIDER}` recipe token;
- linkage `kind` (`static-link`, `dynamic-link`, `runtime-import`,
  `command-exec` or `data-interface`), producing consumer commit and evidence;
- one passing installed-surface record for every canonically ordered edge
  `required_tests` ID, including argv, producing commit, zero exit status and
  evidence;
- private-API `disposition` (`not-used` or `removed`), producing commit and
  evidence; and
- walked rollback argv, producing commit, zero exit status and evidence.

An evidence reference is exactly `evidence_id` plus lowercase nonzero SHA-256.
Every referenced ID must be supplied, no unreferenced ID is accepted, and all
input files must be distinct regular non-symlinks that remain unchanged while
captured. Output is new-file-only and omits local paths and command arguments.
The report proves exact mechanical coverage for 2/2 owner returns and all N/N
staged edges; it grants acceptance for 0/2 owners. Independent owner/release
review still decides whether each retained result actually proves its claim.

Consumers compile only from the staged public prefix: headers beneath
`PREFIX/include`, libraries beneath `PREFIX/lib`, pkg-config metadata beneath
`PREFIX/lib/pkgconfig` or `PREFIX/share/pkgconfig`, and commands beneath
`PREFIX/bin`. A consumer conversion belongs to that consumer's owner; F120 does
not rewrite its worktree. The owner must land linkage choice, installed-surface
tests, every private-API disposition, and a walked rollback before changing the
dependency to `staged-prefix`.

## Release freeze

Do not publish the 0.2.1 closure lock until both external entry conditions are
met: F118's third-party ledger/package freeze and Track C's final
`releases/0.2.1.env`. A pre-freeze lock is disposable mechanism evidence and
must be regenerated wholesale with warm and clean-cache evidence. The final
lock remains an optional refuse-only cross-check, never a selector or grant.
