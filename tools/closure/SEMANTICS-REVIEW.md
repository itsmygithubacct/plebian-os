# F120 v1 companion-semantics review

**Review date:** 2026-08-25
**Status:** frozen clarification; it changes no frozen v1 schema, validator or
fixture byte.

## Inputs

- The complete accepted F120 design and Track H dispatch.
- The byte-frozen package in `contracts/`, including all valid/development/
  invalid fixtures and its independent `SHA256SUMS`.
- `SEMANTICS.md`, the resolver/cache/staging implementation, future-component
  scaffolds, and the locked test/evidence results.

## Review findings and dispositions

| ID | Finding | Disposition |
| --- | --- | --- |
| S01 | v1 did not define which bytes `source_sha256` covers. | Domain-separated committed-tree hashing now defines entry order, length framing, blobs, gitlinks, dirty-byte exclusion and size bounds. Production and an independent test reader derive identical fixture digests. |
| S02 | `instance_id` had syntax but no minting rule. | It is component ID plus the first twelve hex characters of the normalized relative-path SHA-256; owner-supplied unique IDs remain accepted. |
| S03 | `toolchain.digest` could accidentally bind operator paths or omit executable identity. | It hashes sorted logical executable names and exact file digests plus owner-pinned name/version; local paths are verified execution inputs and excluded from metadata. |
| S04 | A build recipe could change without changing frozen build-key inputs. | The canonical complete recipe digest is injected as reserved `build_options.f120_recipe_sha256`; the only resulting cache key remains the frozen validator's derivation. |
| S05 | Inventory vocabulary did not uniquely map to v1 dependency modes. | The five mappings and declaration-only non-edge rule are explicit. A release lock refuses nested/recursive build modes until a conversion actually lands. |
| S06 | The baseline tag exception risked widening into a generic mutable-ref allowance. | Qualification permits exactly `plebian-os`, tag, `v0.2.0`; tag resolution, expected commit, observed HEAD and clean state remain mandatory. Every other branch/tag is refused. |
| S07 | Cache/build prose did not define corruption, path leakage, cancellation or rollback. | Per-key locks, atomic publication, quarantine, bounded subprocess groups, metadata/path rules, exact output audits, exact-key eviction and recoverable stage retirement are defined and tested. |

## Freeze gates

1. `contracts/SHA256SUMS` remains byte-identical and verifies every frozen file.
2. `SEMANTICS.md` is bound by the root `SHA256SUMS`.
3. The frozen validator accepts all original valid fixtures and rejects all
   original invalid fixtures for their named reasons.
4. Production and independent source readers agree.
5. Architecture, options, feature, source and toolchain mutations each change
   the frozen build key.
6. The fixed baseline tag passes and a different tag fails.
7. Cold, warm, concurrent, corrupt, clean-cache and rollback tests pass under
   uv 0.12.5 with the locked dependency graph.
8. A second full run changes no semantic or frozen-package hash.

All gates passed. Incompatible meaning changes require a new companion-semantics
identity and, where accepted-document behavior changes, new frozen contract
schema identities.
