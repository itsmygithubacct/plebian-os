# `kilix.f120.companion-semantics/v3` candidate profile

**Status:** REVIEW CANDIDATE; NOT AUTHORITY  
**Owner decision:** Decision 14, `RATIFY`, 2026-08-26  
**Ratified amendment SHA-256:**
`0e1d8ca1fd330bd47a836ad4f221b1df4e04b670c7af259296d2e90238be039e`

## 1. Normative base and precedence

Sections 3.1 through 3.10 of `RATIFIED-AMENDMENT.md` are incorporated without
qualification as the normative base of
`kilix.f120.companion-semantics/v3`.  The copied file must hash to the digest
above.  This profile supplies only the exact closed release-unit projection,
diagnostic names and candidate command behavior that the ratified text leaves
for the selected contract/profile.  If this profile conflicts with the
ratified text, the ratified text wins and the candidate has a blocking defect.

Frozen registration/v2, workspace-manifest/v1, release-lock/v1 and companion
semantics/v2 remain historical contracts.  No dispatcher may merge, infer or
upgrade between them and this line.  Final 0.2.1 qualification accepts only a
single canonical `kilix.f120.release-lock/v2` document.

## 2. Exact expanded release-unit shape

The registration declaration retains the exact fields ratified in §3.5.  The
release-lock expands it into this closed object:

```json
{
  "artifact_binding_sha256": "A",
  "artifact_descriptor": {
    "artifact_id": "alpha-artifact-descriptor",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/artifact-descriptor"
  },
  "carrier_archive": {
    "artifact_id": "alpha-carrier-archive",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/carrier-archive"
  },
  "carrier_manifest": {
    "artifact_id": "alpha-carrier-manifest",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/carrier-manifest"
  },
  "compliance_binding_sha256": "64-lowercase-hex",
  "compliance_manifest": {
    "artifact_id": "alpha-compliance-manifest",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/compliance-manifest"
  },
  "component_instance": "component-instance",
  "internal_sha256sums": {
    "artifact_id": "alpha-internal-sha256sums",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/internal-sha256sums"
  },
  "license_texts": [
    {
      "artifact_id": "license-apache",
      "artifact_sha256": "64-lowercase-hex",
      "spdx": "Apache-2.0",
      "staged_path": "share/licenses/component/Apache-2.0.txt",
      "text_sha256": "64-lowercase-hex"
    }
  ],
  "modifications": {
    "artifact_id": "alpha-modifications",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/modifications"
  },
  "notices": [
    {
      "artifact_id": "alpha-notice",
      "artifact_sha256": "64-lowercase-hex",
      "kind": "conveyance",
      "path": "source/relative/NOTICE",
      "sha256": "64-lowercase-hex",
      "staged_path": "share/compliance/alpha/NOTICE"
    }
  ],
  "other_notices": [],
  "pair": {
    "artifact_id": "alpha-pair-record",
    "artifact_sha256": "P",
    "staged_path": "share/compliance/alpha/pair-record"
  },
  "pair_digest": {
    "artifact_id": "alpha-pair-digest",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/pair-digest"
  },
  "pair_sha256": "P",
  "payloads": [
    {
      "artifact_id": "payload-alpha",
      "artifact_sha256": "64-lowercase-hex",
      "staged_path": "bin/payload-alpha"
    }
  ],
  "unit_id": "alpha",
  "upstream_notice_inventory": {
    "artifact_id": "alpha-upstream-notice-inventory",
    "artifact_sha256": "64-lowercase-hex",
    "staged_path": "share/compliance/alpha/upstream-notice-inventory"
  }
}
```

The singular named fields correspond exactly to the mandatory exclusive roles.
`payloads`, `license_texts`, `notices` and `other_notices` expand the four
registration arrays.  `path` in a notice remains the committed source path;
`staged_path` is always the final prefix-relative path.  `text_sha256` and
notice `sha256` remain the committed-source digests; `artifact_sha256` is the
measured staged-file digest and must equal the corresponding source digest for
an individually staged licence or notice.

An expanded artifact reference has exactly `artifact_id`, `staged_path` and
`artifact_sha256`.  An expanded licence reference adds exactly `spdx` and
`text_sha256`.  An expanded notice reference adds exactly `kind`, `path` and
`sha256`.  No compact ID-only alternative is accepted in a release lock.

The canonical unit digest is computed after all fields above except
`compliance_binding_sha256` are present:

```text
SHA256(
  UTF8("kilix.f120.compliance-unit/v1") || 0x00 ||
  canonical_f120_json(expanded_unit_without_compliance_binding_sha256)
)
```

Every payload record repeats this exact digest and the same `unit_id` as
`distribution_unit_id`.  A non-payload record carries neither field.

## 3. Registration and workspace projection

The v3 parser is closed.  A component with `build` requires exactly
`commands`, `environment`, `copies`, `artifacts` and `compliance_units`.
Artifact declarations are sorted by unique `artifact_id`; units are sorted by
unique `unit_id`; payload IDs and other-notice IDs are sorted and unique;
licences sort by `(spdx, text_sha256, artifact_id)`; notices sort by
`(path, sha256, kind, artifact_id)`.

Every relative path uses the frozen normalized POSIX grammar: the value must
equal `PurePosixPath(value).as_posix()`, be nonempty and non-absolute, contain
no NUL and contain no `..` segment.  Therefore repeated separators, leading or
embedded `./`, trailing separators and trailing `/.` are invalid encodings,
not alternate identities.  Independently of that syntax refusal, every safe
relative path is normalized with `PurePosixPath(...).as_posix()` before path
uniqueness, staged-artifact, notice-union and copy-closure comparisons.  Thus a
payload at `share//licenses/...` or `share/./licenses/...` collides with a
compliance artifact at `share/licenses/...` as
`F120-V2-DUPLICATE-ARTIFACT-PATH`; string-distinct spellings cannot name one
staged file.

`internal-stage-manifest` is generated by F120 and is forbidden in registration
and workspace artifact declarations.  It is allowed only as a locked generated
artifact and never appears in a unit.

The resolver copies the two arrays exactly into each workspace component and
adds this output-affecting build option:

```text
f120_compliance_declaration_sha256 = SHA256(canonical_f120_json({
  "artifact_declarations": exact_artifact_declarations,
  "compliance_units": exact_compliance_units
}))
```

Registration input may supply neither that name nor `f120_recipe_sha256`.
Resolved components with payload declarations and no units refuse.  Only an
honest unresolved/no-build development component may carry both arrays empty;
that state cannot qualify or enter a release lock.

## 4. Validator boundary

The candidate validator owns JSON shape, canonical bytes, graph integrity,
registration/workspace/release joins, roles, source declaration projection,
unit coverage, union/subset checks, A/P hash joins and the unit binding digest.
It does not reimplement an F100 schema or carrier validator.

Release qualification must call the accepted F100 validators for:

- `kilix.content.compliance-artifact/v1`;
- `kilix.content.compliance-bundle/v1`; and
- `kilix.content.compliance-pair/v1`.

Until F100 publishes an accepted package identity, API identity and
implementation digest for all three, an otherwise F120-valid release lock must
produce `F120-V2-F100-VALIDATOR-UNAVAILABLE`.  F120-owned structural and
semantic defects remain real refusals and cannot be replaced by that temporary
condition.  `--contract-preflight` deliberately
omits those external calls for schema review and prints that its result is not
release qualification.  Individual validation requires an explicit choice
between `--contract-preflight` and `--release-qualification`; there is no
implicit mode whose exit status could be mistaken for the other.  Preflight is
forbidden in P9 and has no permissive fallback.
`--release-qualification` accepts only an exact canonical
`kilix.f120.release-lock/v2` input and is mutually exclusive with `--self-test`
and `--write-hashes`.  Registration and workspace inputs cannot be qualified.
The same exactly-one-mode rule applies to the public library function, not only
to argparse.  Schema errors remain visible alongside safe structural path
checks.  The structural path check is scoped by contract role: it applies the
frozen grammar only at the locations the published schemas declare a `path`,
`staged_path` or `text_path`, so a user-chosen key inside the open
`build_options` map is not a contract path.  If malformed input aborts any
check that reads untrusted document shape -- the registration parser and the
schema and path passes as well as the deeper joins -- the validator returns
`F120-V2-VALIDATOR-FAILURE` rather than exposing a traceback.  Nesting beyond
the safe canonicalization depth is `F120-V2-LOAD`, and a schema identity that
is not a string is `F120-V2-SCHEMA-IDENTITY`: an identity is compared, never
used as a dictionary or set key.  Missing
or unreadable manifest-bound package members likewise return a named package
inventory or hash-manifest refusal.

## 5. Stable named refusal families

The implementation and mutation corpus must retain these names (details may
append subject identifiers):

- `F120-V3-SCHEMA-IDENTITY` and `F120-V2-SCHEMA-IDENTITY`;
- `F120-V3-RESERVED-BUILD-OPTION`;
- `F120-V3-DECLARED-INTERNAL-MANIFEST`;
- `F120-V2-ZERO-NOTICE-CARRIER`;
- `F120-V2-PAYLOAD-WITHOUT-UNIT`;
- `F120-V2-UNKNOWN-ARTIFACT`;
- `F120-V2-CROSS-COMPONENT-REFERENCE`;
- `F120-V2-ROLE-MISMATCH`;
- `F120-V2-LICENCE-TUPLE-MISMATCH`;
- `F120-V2-NOTICE-TUPLE-MISMATCH`;
- `F120-V2-LICENCE-UNION-MISMATCH`;
- `F120-V2-NOTICE-UNION-MISMATCH`;
- `F120-V2-ORPHAN-COMPLIANCE-ARTIFACT`;
- `F120-V2-EXCLUSIVE-COMPLIANCE-ARTIFACT`;
- `F120-V2-ARTIFACT-BINDING-MISMATCH`;
- `F120-V2-PAIR-DIGEST-MISMATCH`;
- `F120-V2-STAGED-ARTIFACT-MISMATCH`;
- `F120-V2-COMPLIANCE-BINDING-MISMATCH`;
- `F120-V2-F100-VALIDATOR-UNAVAILABLE`;
- `F120-V2-PATH`;
- `F120-V2-VALIDATION-MODE`; and
- `F120-V2-VALIDATOR-FAILURE`.

Schema errors are additional evidence and never replace the named semantic
refusal for a known adversarial shape.  In particular, the migrated original
F120-C11 payload-only/zero-notice counterexample must name
`F120-V2-ZERO-NOTICE-CARRIER` before any candidate prefix or lock is exposed.

## 6. Freeze boundary

R4 was rejected by root adjudication at 0C/0H/1M/1L after its cross-family pair
independently confirmed the R3 High closed.  R5 closes both: it scopes the
supplemental path walk to the schema-declared contract path fields, leaving the
path grammar and every normalized comparison join unchanged, and it makes the
pre-semantic and registration boundaries abort into stable named refusals
rather than tracebacks.  No R4 review transfers to R5.
This R5 package becomes authority only if both fresh
independent contract reviews
accept the same complete `SHA256SUMS` bytes with zero open findings and the
two-pass no-drift gate passes.  Local self-review or deterministic regeneration
alone is not either independent acceptance.  Production resolver/stager work
must be based on the accepted package identity, not on mutable candidate files.
The complete package census is recursive and excludes only `SHA256SUMS` itself
and the top-level `.venv` review-run environment; any other unlisted regular
file, symlink or special member is a refusal.
