# F120 v3/v2/v2 licence-carrier correction candidate

This directory is the **R4 correction candidate, not contract authority and
not release qualification evidence**.  It implements the contract-design gate
selected by Owner Decision 14 without changing one byte in the frozen v1
package at `../contracts/`.  Root adjudication rejected R3 after Review 1
accepted at zero findings and Review 2 returned one High and two Low findings.
The adjudication records all eight R2 return conditions closed; R4 retains those
corrections and closes the three new findings.  No R2 or R3 review transfers to
these changed bytes.

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
the former accepted zero-notice shape and an internally re-bound release lock
whose payload path aliases its own unit's readable licence path.

Run the deterministic contract-only gate with:

```sh
uv run --locked python build_candidate.py --check
uv run --locked python validate_candidate.py --self-test
```

Individual validation has no implicit mode.  It requires exactly one of
`--contract-preflight` and `--release-qualification`, so a successful preflight
cannot be consumed as a release-qualification result by exit status alone at
either the CLI or library boundary.  All relative paths use the frozen
normalized POSIX grammar in the registration parser, both schemas and the
release joins.  The semantic joins additionally normalize safe relative paths
before every identity comparison, so `share//licenses/...` and
`share/./licenses/...` collide with `share/licenses/...` even though their raw
strings differ.  Alternate spellings cannot create distinct identities for one
staged file.  Schema-invalid documents cannot escape through a traceback: deep
semantic failures and package-census read failures return stable named
refusals.
Qualification is bound to an exact `kilix.f120.release-lock/v2` input and is
mutually exclusive with construction and self-test actions.
`--contract-preflight` is deliberately named and printed as non-qualifying.  An
explicit release validation refuses with
`F120-V2-F100-VALIDATOR-UNAVAILABLE` until F100 publishes accepted validator
and API identities.  There is no permissive fallback, embedded substitute or
test stub.  Independent reviewers must accept the exact candidate bytes before
the identities can become authority or be integrated into the resolver.
