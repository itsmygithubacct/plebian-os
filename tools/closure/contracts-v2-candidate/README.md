# F120 v3/v2/v2 licence-carrier correction candidate

This directory is a **fresh correction candidate, not contract authority and
not release qualification evidence**.  It implements the contract-design gate
selected by Owner Decision 14 without changing one byte in the frozen v1
package at `../contracts/`.  The preceding exact bytes were not accepted after
two reviews found three open Low findings.  Reviews of those bytes do not
transfer to this candidate.

The candidate is bound to the exact owner-ratified amendment copied as
`RATIFIED-AMENDMENT.md`, whose required SHA-256 is
`0e1d8ca1fd330bd47a836ad4f221b1df4e04b670c7af259296d2e90238be039e`.
If those bytes differ, the owner ratification does not apply.

The closed candidate identities are:

- `kilix.f120.registration/v3`;
- `kilix.f120.workspace-manifest/v2`;
- `kilix.f120.release-lock/v2`; and
- `kilix.f120.companion-semantics/v3`.

`PROFILE.md` fixes the release-lock expansion left for the contract/profile to
select.  The two Draft 2020-12 schemas are in `schemas/`.  The registration
parser and both document validators are represented by
`validate_candidate.py`; the registration remains a closed implementation
input rather than a third published JSON Schema.

`build_candidate.py` derives the schemas from the frozen v1 schemas in memory
and emits canonical fixtures.  It never writes in `../contracts/`.  The valid
corpus contains three distribution units in one component: two have different
licence obligations, while the third deliberately groups two uniformly
obligated payloads.  Invalid fixtures carry stable named refusals, including
the former accepted zero-notice shape.

Run the deterministic contract-only gate with:

```sh
uv run --locked python build_candidate.py --check
uv run --locked python validate_candidate.py --self-test
```

Individual validation has no implicit mode.  It requires exactly one of
`--contract-preflight` and `--release-qualification`, so a successful preflight
cannot be consumed as a release-qualification result by exit status alone.
`--contract-preflight` is deliberately named and printed as non-qualifying.  An
explicit release validation refuses with
`F120-V2-F100-VALIDATOR-UNAVAILABLE` until F100 publishes accepted validator
and API identities.  There is no permissive fallback, embedded substitute or
test stub.  Independent reviewers must accept the exact candidate bytes before
the identities can become authority or be integrated into the resolver.
