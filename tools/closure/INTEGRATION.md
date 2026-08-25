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
   only argv placeholders `{source}`, `{build}`, `{prefix}` and `{tool:name}`.
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
8. Run `stage` twice against one cache and once against an empty independent
   cache. The warm run must report zero fetches, zero `fetch_bytes`, and zero
   builds. All staged bytes and the validated locks must match the clean-cache
   run.

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
