# F120 v1 contract review

**Review date:** 2026-08-19
**Status:** **frozen v1**; every gate below passed with `uv run --locked`

## Inputs reviewed

- Accepted F120 plan:
  `../0.2.1-MONOREPO-SHARED-LIBRARY-EFFICIENCY.md`.
- Provider baseline report:
  `../0.2.1-F120-PROVIDER-INVENTORY.md`.
- Machine evidence:
  `../0.2.1-F120-PROVIDER-INVENTORY.json`, SHA-256
  `0bcfac754ce1f8ee3953aa2a5d127590f8f2f23666800db33183a0a1697f2ba7`.
- Both candidate schemas, all golden fixtures, the validator, README,
  `pyproject.toml`, and `uv.lock` in this directory.

The review compares the contracts with the plan's E1 graph/lock requirements
and with the baseline's observed multiple commits, dirty gitlinks,
uninitialized submodules, local origins, recursive consumption, and native
provider diamonds. It does not review or authorize a resolver implementation.

## Findings and dispositions

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| F120-C01 | High | The original workspace schema required `requested_ref` to be a commit, so it could not honestly record a branch/tag development checkout or distinguish requested ref, expected gitlink, and locally resolved HEAD. | **Fixed.** v1 records `ref_kind`, free-form `requested_ref`, exact `expected_commit`, optional resolved commit, dirty state, and resolution state. Development mode records mutable/unresolved state; qualification rejects it and all commit mismatches. |
| F120-C02 | High | `build_key_sha256` was arbitrary and therefore did not bind a staged artifact to source, architecture, toolchain, features, and build options. | **Fixed.** The validator derives and verifies a canonical build-key digest; source, architecture, toolchain, feature, licence, and artifact digests remain independently bound. |
| F120-C03 | High | Dependency edges lacked API/ABI compatibility constraints, so a lock could join incompatible exact revisions while remaining structurally valid. | **Fixed.** Every edge carries exact required API and ABI versions and validation matches them to the target instance. Ranges are deliberately excluded from v1 release locks. |
| F120-C04 | Medium | Native diamond detection treated every duplicated component identity as native, which could reject permitted separately loaded Python/data/process versions. | **Fixed.** Components declare `runtime_kind`; conflicting revisions fail only for native providers participating in the same named runtime process. |
| F120-C05 | Medium | Build options and notice identity were absent even though the accepted plan makes both part of source/build/licence closure. | **Fixed.** Components carry typed build options and sorted notice path/digest records; build options participate in artifact build-key binding. |
| F120-C06 | Medium | Staged artifacts lacked a type, making headers, libraries, commands, Python packages, pkg-config data, notices, manifests, and ordinary data indistinguishable. | **Fixed.** `artifact_kind` is required with a closed v1 enumeration. Each release component must still produce at least one bound artifact. |
| F120-C07 | Medium | The loader accepted duplicate JSON keys and unbounded documents; different parsers could interpret a malicious lock differently. | **Fixed.** The standalone validator rejects duplicate keys and documents over 4 MiB before schema or graph processing; self-tests exercise both. |
| F120-C08 | Medium | URI format alone did not establish canonical identity and publication could conflict with visibility. | **Fixed.** Schema requires HTTPS; semantic validation rejects credentials, query, fragment, missing/lowercase-host violations and rejects `publish` unless visibility is public. |
| F120-C09 | Medium | Validation dependencies were resolved ephemerally with `--no-project`, so a future jsonschema release could change results. | **Fixed.** The package has an exact dependency, reproducible `uv.lock`, and only `uv run --locked` instructions. |
| F120-C10 | Low | Invalid fixtures were accepted as successful tests if they failed for an unrelated reason. | **Fixed.** Each invalid fixture has a required diagnostic substring and the test runner rejects fixture/expectation drift. |

No finding is undispositioned. No fetched source, generated artifact, consumer
pin, Plebian OS integration, or release worktree is an input to the validator.

## v1 freeze gates

All must pass in one final run:

1. Both schemas pass Draft 2020-12 meta-schema validation with format checking.
2. JSON is canonical; deterministic `SHA256SUMS` binds the complete package.
3. Two qualified fixtures pass and the development-state fixture passes only
   with `--allow-development-state`.
4. Every invalid golden fixture fails for its named reason.
5. Duplicate-key and oversized-document adversarial tests pass.
6. Exact commit/digest, canonical URL/visibility, component/API/ABI versions,
   architecture/toolchain/features/build options, licences/notices/publication,
   dependency/consumption/test edges, cycles, mutable refs, dirty/unresolved
   state, native diamonds, and staged-artifact bindings are represented and
   exercised.
7. `uv lock --check` and the full suite pass with `uv run --locked`.
8. A second full run without file changes produces the same package hashes.
9. No `.venv`, bytecode, resolver, fetch/build implementation, pin change, or
   0.2.0/Plebian OS/master edit is included in the package.

## Freeze result

All nine gates passed on 2026-08-19. The final run used the committed lock,
accepted both qualified fixtures, accepted the development fixture only under
its explicit flag, rejected all seven invalid fixtures for their named reason,
passed duplicate-key and 4 MiB size-limit adversarial checks, verified canonical
JSON and the complete deterministic hash manifest, and repeated without byte
drift. The v1 schemas are therefore frozen. Incompatible evolution requires new
schema identities rather than changing v1 semantics.
