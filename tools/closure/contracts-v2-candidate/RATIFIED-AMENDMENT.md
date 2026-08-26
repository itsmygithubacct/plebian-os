# F120 licence/notice carrier amendment — owner-ratifiable proposal

**Prepared:** 2026-08-25  
**Finding:** F120-C11  
**Status:** **PROPOSED; NOT RATIFIED; NOT IMPLEMENTED**  
**Authority requested:** release owner and frozen F120 contract owner  
**Effect if ratified:** authorize a new, incompatible F120 contract line; do
not edit or reinterpret the frozen v1 bytes

## 1. Decision requested

The current two layers are both incomplete:

- F100 specifies a per-artifact readable licence/notice carrier, but neither
  install path implements it; and
- frozen F120 v1 can preserve component licence/notice declarations while
  accepting a staged payload that carries none of the declared text bytes.

F120-C11 proves the second defect with an accepted counterexample. A component
declared a licence text and notice, while the valid staged prefix contained
only a payload and generated stage manifest. `artifact_kind: notice` being
available did not make a notice mandatory or bind it to a payload.

This proposal selects the exact-artifact route rather than the strict-v1
workaround. It creates new schema identities and one explicit distribution-unit
join. It is deliberately incompatible: per-component unions are preserved for
inventory, but may no longer stand in for per-artifact conveyance.

The owner may ratify or reject the following exact text. Track H must not land
schema/code changes from this proposal without that decision and a new
two-pass contract review.

## 2. Exact owner ratification text

The proposed owner record is the following verbatim block:

> **F120-C11 OWNER DECISION — ACCEPT NEW LICENCE-CARRIER CONTRACT LINE**
>
> I authorize Track H to produce and qualify the incompatible contract
> identities `kilix.f120.registration/v3`,
> `kilix.f120.workspace-manifest/v2`,
> `kilix.f120.release-lock/v2`, and
> `kilix.f120.companion-semantics/v3`, implementing the normative amendment in
> `0.2.1-F120-LICENCE-CARRIER-AMENDMENT.md`.
>
> Frozen workspace-manifest/release-lock v1 and registration/v2 remain
> byte-frozen historical S120 inputs. They are not amended, reinterpreted or
> silently upgraded. They remain acceptable for their previously published
> development/inventory role, but no v1 document may qualify, describe as
> complete, or authorize inclusion of a redistributed 0.2.1 artifact.
>
> The final 0.2.1 P9 release lock is one canonical
> `kilix.f120.release-lock/v2` document. It contains no embedded v1 component
> or artifact records. Every redistributed payload artifact belongs to exactly
> one same-component distribution unit whose exact payload set is bound to a
> complete staged compliance carrier: descriptor, compliance manifest, full
> licence texts, conveyance and upstream/other notices, modification record,
> notice inventory, sums, carrier archive and manifest, pair record and pair
> digest. A component-wide licence digest is necessary but is not evidence of
> conveyance.
>
> F120 must verify the exact staged bytes, references, component ownership,
> obligation coverage and binding digests before it emits or accepts the lock.
> The release assembler, installer handoff, export, mirror and retirement paths
> must treat the payload and its carrier closure as one inseparable
> distribution unit. Missing, ambiguous, cross-component, unreferenced,
> borrowed or mismatched material fails closed.
>
> F100 remains the authority for
> `kilix.content.compliance-artifact/v1`,
> `kilix.content.compliance-bundle/v1` and
> `kilix.content.compliance-pair/v1`. F120 calls the accepted F100 validators
> and binds their results; it does not fork those formats or infer licence
> obligations. Stream owners remain responsible for payload inventories,
> determinations, notice content and modification truth.
>
> Ratification authorizes contract implementation and independent review only.
> It does not admit a model, authorize redistribution, close F100 carrier
> implementation, change a consumer pin, publish a contract candidate, or
> close P9. New bytes become authority only after the required freeze,
> implementation, mutation campaign, consumer migration and combined review
> accept the exact new identities.

## 3. Normative amendment text

The following text is proposed verbatim for
`kilix.f120.companion-semantics/v3`. RFC-style **MUST**, **MUST NOT**, **SHALL**,
**SHALL NOT**, **SHOULD** and **MAY** are normative.

### 3.1 Contract identity and compatibility

> F120 licence conveyance uses the closed identities
> `kilix.f120.registration/v3`,
> `kilix.f120.workspace-manifest/v2` and
> `kilix.f120.release-lock/v2`. The corresponding companion identity is
> `kilix.f120.companion-semantics/v3`.
>
> These identities are incompatible with registration/v2 and workspace/
> release v1. A v1/v2 parser MUST reject the new identities and unknown fields;
> a v3/v2 parser MUST reject an older identity on a release-qualification path.
> A dispatcher MAY retain exact old parsers for historical development
> evidence, but MUST select a parser solely by the exact top-level `schema`
> value and MUST NOT normalize, infer, merge or upgrade fields between
> identities.
>
> The final 0.2.1 release lock MUST be one canonical
> `kilix.f120.release-lock/v2` document. A mixed-version document and a v1 lock
> adjacent to a v2 compliance file are invalid.

### 3.2 Terms

> A **payload artifact** is a regular staged artifact delivered for use by a
> consumer or user. Commands, headers, libraries, Python packages, pkg-config
> files and data are payload artifacts unless the registration assigns one of
> the closed compliance or internal roles below.
>
> A **distribution unit** is one non-empty, same-component set of payload
> artifact IDs and the complete compliance carrier that applies to exactly
> those payload bytes. Every payload artifact MUST belong to exactly one
> distribution unit. Multiple distribution units MAY exist in one component
> and MAY carry different obligation sets.
>
> A **compliance artifact** is a staged regular file with one closed
> `artifact_role` other than `payload` or `internal-stage-manifest`. Compliance
> artifacts are content, not URLs, package-manager metadata or receipts that
> merely contain a digest.
>
> A **carrier closure** is every compliance artifact referenced by one
> distribution unit. The carrier closure and its payload set are inseparable
> for release-lock admission, export, mirror, installation handoff and
> retirement.

### 3.3 Component licence and notice declarations

> Each v3/v2 component `licenses` entry MUST have exactly the fields `spdx`,
> `text_path` and `text_sha256`. `text_path` is a component-relative committed
> source path. A qualified resolve MUST open that exact committed regular blob,
> hash its bytes and require equality with `text_sha256`. A URL, system common-
> licence path or unverified digest is not a licence text.
>
> Each component `notices` entry retains exactly `path` and `sha256`. A
> qualified resolve MUST verify those committed bytes as before. The mandatory
> artifact-specific conveyance `NOTICE`, `MODIFICATIONS` and reviewed upstream-
> notice inventory MUST be declared notice/compliance inputs even when the
> reviewed upstream tree contains no file named `NOTICE`.
>
> Component arrays are the union inventory. They MUST NOT be used as the
> per-payload obligation answer. The exact licence and notice subset applicable
> to a distribution unit is the unit's `license_texts` and `notices` arrays.

### 3.4 Closed artifact roles

> Every declared or locked artifact MUST carry exactly one `artifact_role`
> from this closed set:
>
> ```text
> payload
> artifact-descriptor
> compliance-manifest
> license-text
> conveyance-notice
> upstream-notice
> other-notice
> modifications
> upstream-notice-inventory
> internal-sha256sums
> carrier-archive
> carrier-manifest
> pair-record
> pair-digest
> internal-stage-manifest
> ```
>
> `internal-stage-manifest` is generated by F120 and MUST NOT appear in a
> distribution unit. `payload` MUST appear in exactly one unit. A compliance
> artifact MUST be referenced by at least one unit in its component; an orphan
> compliance artifact is invalid. Exact licence-text bytes MAY be shared by
> more than one same-component unit. `pair-record`, `pair-digest`,
> `carrier-archive`, `carrier-manifest`, `artifact-descriptor`,
> `compliance-manifest`, `modifications`,
> `upstream-notice-inventory` and `internal-sha256sums` MUST be exclusive to
> one unit.
>
> Existing `artifact_kind` remains the physical/API classification. The
> semantic validator MUST enforce a compatible kind/role pair and MUST reject
> a command, library, header, Python package or pkg-config artifact assigned a
> compliance role.

### 3.5 Registration/v3 declaration

> Every resolved component with a `build` MUST declare `build.artifacts` and
> `build.compliance_units`. Every artifact declaration has exactly
> `artifact_id`, `artifact_kind`, `artifact_role`, `path` and, for every
> non-payload/non-internal role, `expected_sha256`. A payload MAY also carry an
> `expected_sha256`; if present, the staged bytes MUST match it.
>
> `build.compliance_units` is sorted by unique `unit_id`. Each entry has
> exactly this semantic shape:

```json
{
  "artifact_binding_sha256": "64-lowercase-hex",
  "artifact_descriptor_artifact_id": "artifact-id",
  "carrier_archive_artifact_id": "artifact-id",
  "carrier_manifest_artifact_id": "artifact-id",
  "compliance_manifest_artifact_id": "artifact-id",
  "internal_sha256sums_artifact_id": "artifact-id",
  "license_texts": [
    {
      "artifact_id": "artifact-id",
      "spdx": "Apache-2.0",
      "text_sha256": "64-lowercase-hex"
    }
  ],
  "modifications_artifact_id": "artifact-id",
  "notices": [
    {
      "artifact_id": "artifact-id",
      "kind": "conveyance",
      "path": "source/relative/NOTICE",
      "sha256": "64-lowercase-hex"
    }
  ],
  "other_notice_artifact_ids": [],
  "pair_artifact_id": "artifact-id",
  "pair_digest_artifact_id": "artifact-id",
  "pair_sha256": "64-lowercase-hex",
  "payload_artifact_ids": ["one-or-more-artifact-ids"],
  "unit_id": "component-local-stable-id",
  "upstream_notice_inventory_artifact_id": "artifact-id"
}
```

> All object shapes are closed. IDs use the existing F120 identifier grammar;
> digests use the existing lowercase SHA-256 grammar; paths use the existing
> relative-path grammar. Arrays are non-empty unless shown as an empty array,
> sorted and unique by their semantic key. `license_texts` is sorted by
> `(spdx, text_sha256, artifact_id)`. `notices` is sorted by
> `(path, sha256, kind, artifact_id)`. `kind` is one of `conveyance`,
> `upstream`, `attribution` or `other`. Exactly one notice has kind
> `conveyance`.
>
> `pair_sha256` is `P`, the SHA-256 of the exact canonical F100 compliance-pair
> bytes. `artifact_binding_sha256` is `A`, the SHA-256 of the exact canonical
> F100 `ARTIFACT.json` bytes. The artifact whose ID is `pair_artifact_id` MUST
> have role `pair-record` and expected SHA-256 `P`. The artifact whose ID is
> `artifact_descriptor_artifact_id` MUST have role `artifact-descriptor` and
> expected SHA-256 `A`.
>
> An unresolved development component without `build` emits empty
> `artifact_declarations` and `compliance_units`; it cannot qualify or enter a
> release lock. No placeholder digest, all-zero artifact ID or guessed carrier
> is permitted.

### 3.6 Workspace-manifest/v2 projection

> Each workspace-manifest/v2 component carries required
> `artifact_declarations` and `compliance_units` arrays copied from the exact
> accepted registration. The resolver MUST NOT invent, drop, merge or broaden
> a unit. It MUST verify `licenses[].text_path`/`text_sha256` and every notice
> source blob at the same resolved commit used for `source_sha256`.
>
> The canonical digest of the complete artifact declarations and compliance
> units is injected into the reserved output-affecting build option
> `f120_compliance_declaration_sha256`. Registration input MUST NOT supply that
> reserved name. Any change to a role, path, reference, `A`, `P`, licence or
> notice changes the frozen build key.
>
> Qualification refuses empty units for a component that declares payload
> artifacts, any payload in zero or multiple units, a reference to an unknown
> artifact, a cross-component reference, a role mismatch, an unverified source
> text, an unused component licence/notice entry or an obligation named by no
> unit.

### 3.7 Release-lock/v2 artifact and unit records

> Release-lock/v2 retains the v1 top-level `components`, `dependencies` and
> `artifacts` fields and adds required `compliance_units`. Every component
> carries the v2 licence shape. Every artifact retains all v1 binding fields and
> adds required `artifact_role`. A payload artifact also carries required
> `distribution_unit_id` and `compliance_binding_sha256`. No other role may
> carry `distribution_unit_id`.
>
> Each release `compliance_units` record expands the registration declaration
> with the actual `artifact_id`, staged `path` and `artifact_sha256` of every
> referenced payload and compliance artifact. It carries
> `component_instance`, `unit_id`, `artifact_binding_sha256`, `pair_sha256` and
> `compliance_binding_sha256`. It is sorted by
> `(component_instance, unit_id)` and is a closed object.
>
> `compliance_binding_sha256` is computed exactly as:
>
> ```text
> SHA256(
>   UTF8("kilix.f120.compliance-unit/v1") || 0x00 ||
>   canonical_f120_json(expanded_unit_without_compliance_binding_sha256)
> )
> ```
>
> `canonical_f120_json` is the existing F120 UTF-8, two-space-indented,
> sorted-key JSON representation with one final LF, duplicate keys and
> non-finite/non-integer numbers refused. The digest has no self-reference.
> Every payload artifact in the unit repeats that exact digest.
>
> `licenses_sha256` remains on every artifact as the digest of the component's
> union licence array. It is not removed and does not replace
> `compliance_binding_sha256`.

### 3.8 Required semantic joins

> The v2 validator MUST enforce all of the following over the whole document:
>
> 1. artifact IDs and paths are globally unique under the existing rules;
> 2. every referenced artifact exists and has the required same component,
>    role, path and measured SHA-256;
> 3. every payload artifact occurs in exactly one distribution unit;
> 4. every non-shared compliance artifact occurs in exactly one unit and every
>    shared licence/notice artifact remains in the same component;
> 5. each `license_texts` tuple exactly matches one component licence tuple and
>    the referenced role=`license-text` artifact digest equals
>    `text_sha256`;
> 6. each `notices` tuple exactly matches one component notice tuple and the
>    referenced notice artifact digest equals `sha256`;
> 7. the union of unit licence tuples equals the component licence array, and
>    the union of unit notice tuples equals the component notice array;
> 8. each unit contains exactly one conveyance notice and the mandatory
>    descriptor, compliance manifest, modifications, notice inventory,
>    internal sums, carrier archive, carrier manifest, pair and pair digest;
> 9. the exact `pair-record` bytes validate as
>    `kilix.content.compliance-pair/v1` using the accepted F100 validator;
> 10. the pair bytes hash to `P`, name the same `A`, payload identity, carrier
>     archive/manifest and licence decisions, and the pair-digest artifact
>     contains the exact permitted LF-terminated `P` line;
> 11. the exact artifact-descriptor bytes hash to `A`, and their complete member
>     inventory equals the unit's payload artifacts by identity, bytes and
>     digest;
> 12. the unpacked carrier tree validates against the exact archive, adjacent
>     manifest, internal sums and all individually staged compliance files;
>     an archive containing a text is not a substitute for the individually
>     staged readable text;
> 13. all paths are regular, no-follow, bounded, inside the exact staged prefix
>     and have the required final readability/mode disposition; and
> 14. the recomputed expanded-unit digest equals the unit and every payload
>     artifact `compliance_binding_sha256`.
>
> F120 MUST call the accepted F100 validators for the F100-owned schemas. It
> MUST bind their exact package/API version and implementation digest as a P9
> tool input. Reimplementation or permissive fallback is forbidden. If the
> validator is missing, incompatible or returns an unknown result, P9 refuses.

### 3.9 Staging and conveyance

> Build-cache and staged-prefix verification MUST treat every declared carrier
> file as an ordinary exact output. A recipe that emits only payload files is
> incomplete. Staging MUST finish and reverify the complete carrier closure
> before publishing or exposing any payload path.
>
> Any release assembler, exporter, mirror, installer handoff or packaging step
> selecting one payload artifact MUST select every payload and compliance
> artifact in its distribution unit and MUST bind the unit's
> `compliance_binding_sha256`. It MUST NOT select by component-wide
> `licenses_sha256`, SPDX identifier, nearest filename, shared family name or
> mutable tag.
>
> A system-seed and per-user carrier MAY be installed at the closed paths in
> `0.2.1-LICENCE-NOTICE-CARRIER-SPEC.md`, but F120 does not install them. F120
> proves that the release handoff contains the exact carrier unit; F100 owns
> presentation, receipt joining, atomic installed selection and model-lifetime
> retention.
>
> Retirement MUST refuse removal of a carrier artifact while any payload,
> retained release unit, rollback selection or external retention proof names
> its unit. A payload MUST NOT remain selected or distributable if its carrier
> closure is missing or invalid.

### 3.10 Bounds and canonical form

> Existing F120 document, string, path and array bounds continue to apply.
> Additionally: a component has at most 16,384 artifact declarations and 4,096
> compliance units; a unit has at most 16,384 payload IDs, 256 licence entries,
> 4,096 notice entries and 4,096 other-notice IDs. Empty payload, licence and
> notice arrays are invalid. JSON duplicate keys, unknown fields, booleans in
> numeric fields, non-integers, values outside declared bounds, non-canonical
> ordering and non-canonical bytes are refused before semantic joins.

## 4. Proposed schema field amendments

This section is part of the ratifiable contract, not an implementation hint.
The eventual Draft 2020-12 schemas must express every rule they can express;
the companion validator owns the cross-record and byte-level joins.

### 4.1 Registration/v3

Registration is an implementation input rather than one of the two currently
published JSON Schemas, but its parser is closed and versioned. The exact v3
delta is:

- `REGISTRATION_ID` becomes `kilix.f120.registration/v3` for the new parser;
- `licenses[]` requires `text_path` in addition to `spdx` and `text_sha256`;
- every `build.artifacts[]` requires `artifact_role` and conditionally requires
  `expected_sha256` as §3.5 states;
- every build requires `compliance_units` in addition to `commands`,
  `environment`, `copies` and `artifacts`; and
- `f120_compliance_declaration_sha256` is a reserved generated build option.

The v2 parser remains a separate exact parser. It is not modified to accept
the v3 fields.

### 4.2 Workspace-manifest/v2

The v2 schema is copied from frozen workspace-manifest/v1 and changed only by
the new `$id`, comment, licence shape, and these required component properties:

```json
{
  "artifact_declarations": {
    "items": {"$ref": "#/$defs/artifactDeclaration"},
    "maxItems": 16384,
    "type": "array"
  },
  "compliance_units": {
    "items": {"$ref": "#/$defs/complianceUnitDeclaration"},
    "maxItems": 4096,
    "type": "array"
  }
}
```

Both fields are required on every component. They are empty only for honest
unresolved/no-build development components; qualification semantics reject
that state.

### 4.3 Release-lock/v2

The v2 schema is copied from frozen release-lock/v1 and changed only by the new
`$id`, comment, licence shape, artifact fields/conditionals and required
top-level `compliance_units`:

```json
{
  "compliance_units": {
    "items": {"$ref": "#/$defs/expandedComplianceUnit"},
    "maxItems": 16384,
    "minItems": 1,
    "type": "array"
  }
}
```

Every artifact requires `artifact_role`. A role=`payload` artifact requires
`distribution_unit_id` and `compliance_binding_sha256`; every other role
forbids both. The schema continues to set `additionalProperties: false` at
every object.

## 5. Required freeze and acceptance evidence

Ratification does not make the prose executable. Track H must produce, and two
independent reviews must accept, all of the following before the new identities
become authority:

1. three complete parsers/validators and two Draft 2020-12 schema files;
2. byte-frozen companion semantics and deterministic `SHA256SUMS`;
3. valid registration/workspace/release golden fixtures with at least two
   differently obligated units in one component;
4. a uniform-obligation multi-payload unit proving intentional grouping;
5. the exact F104 CAM++ modified-output carrier and one F105 pair as positive
   cross-module fixtures;
6. the original F120-C11 accepted counterexample changed to the exact named
   refusal before stage publication;
7. one invalid fixture/mutation for every join in §3.8;
8. missing licence text, notice, modifications, inventory, pair and individual
   readable-file refusals;
9. cross-component, borrowed-same-SPDX, ambiguous, duplicate, orphan and
   unreferenced-carrier refusals;
10. wrong A/P, pair line, archive, member, source path, staged path, digest,
    role and unit-binding refusals;
11. payload-only selection/export/install-handoff and carrier-only retirement
    refusals;
12. component-union-equal but wrong per-unit subset refusal;
13. one-byte mutation in every carrier role, duplicate-key and canonical-byte
    controls, and exact maximum/overflow tests;
14. cold, warm, concurrent and independent-clean stage equality with the
    compliance declaration in the build key;
15. crash/cancellation at every cache, stage, lock and paired-publication cut,
    proving no exposed payload without its carrier;
16. source, sdist, wheel and installed validator equivalence, wheel without test
    authority, safe archives and reproducible artifacts;
17. v1 historical self-tests remain byte-identical and green under their old
    parser;
18. P9 refuses a final v1 lock and accepts only the exact v2 identity;
19. migrated public pilot evidence plus every development scaffold; and
20. a retained artifact-by-artifact/unit-by-unit matrix linking payload hashes,
    A, P, licence texts, notices and final staged paths.

Acceptance requires zero open Critical, High, Medium or Low findings. A green
schema fixture alone is insufficient; each fail-closed claim needs a mutation
that removes the claimed subject and produces the expected named refusal.

## 6. What breaks in already-published consumers

The table separates actual published consumers from local/unpublished work.
Adopting a new identity must not be described as a compatible clarification.

| Published surface | Exact published identity | What breaks when v2/v3 becomes the P9 requirement | Required migration |
| --- | --- | --- | --- |
| **Plebian OS F120 closure producer/parser** | public S120 commit `429504c2bbc7b330e40cec97eec226e59c194e38`, tree `7d8a9c0c1e4c719d2863f6a42206cff040f6d807` | `registration.py` accepts only registration/v2; `contracts.py` and frozen schemas accept only workspace/release v1; `manifest.py`, `stage.py`, `release.py` and `validate_f120.py` neither emit nor validate the new fields. Existing parsers correctly reject v2/v3 as unknown. Existing stage/cache keys omit the compliance declaration and existing valid prefixes may contain no carrier. | Publish a new Track H commit containing separate new parsers/schemas, v3 registration, v2 projection/stage/lock/audit, trusted launcher and full §5 evidence. Preserve `429504c` as historical S120; never rewrite it. Old caches/prefixes are evidence only and cannot be promoted into P9 v2. |
| **`kilix-object-detect` pilot consumer** | public `main` `5b0131dd83ea744271964fb5787deba424e3029b`, consuming the staged `kilix-motion-detect` surface | Its C source and staged-prefix build do not parse F120 JSON and do not break at compile/runtime. Its retained two-component registration/workspace/lock evidence is v2/v1 and cannot qualify under the new line. Its current recipe stages payload outputs without a carrier, so the compliance declaration changes the recipe/build-key and invalidates old stage identity. | Owner supplies exact v3 fragments for consumer and provider, declared licence text/notice carrier units, and reruns cold/warm/clean, installed-surface and rollback evidence. Functional source need not change unless packaging currently omits the required readable files. |
| **F106 system-monitor development scaffold** | `tools/closure/fixtures/registrations/f106-system-monitor.json` at `429504c`, SHA-256 `ec907433184ac6e4e6fa583ff8987c195d9bb7615b71ae0a794a3710bba11277` | It says registration/v2, its licence entries lack `text_path`, and all three unresolved components have no artifact declarations or compliance units. The v3 parser must reject it on a qualification path. | Keep the exact old fixture for v1 regression evidence. Add a separately named v3 development fixture with verified licence paths and explicit empty arrays; later replace its zero-commit/no-build state with owner-supplied exact distribution units before P9. |
| **F110 desktop-SDK development scaffold** | `tools/closure/fixtures/registrations/f110-desktop-sdk.json` at `429504c`, SHA-256 `bafed964768835737d1df28010c187f91529fcc7cfa5d36324453c97e9eb84a4` | Same identity/field failure. Its five disconnected, unresolved nodes cannot be silently translated into v3 units, and the existing fixture also does not represent the separate `kilix-icewm` consumer. | Preserve the v1 fixture, add a v3 development fixture, and obtain final owner fragments for every selected SDK unit and the separate IceWM repository. Final carrier units must follow actual package boundaries; the fixture cannot invent them. |
| **F111 media-SDK development scaffold** | `tools/closure/fixtures/registrations/f111-media-sdk.json` at `429504c`, SHA-256 `d258f6aa0a96496827c95eaddcae9688eccaf8d11dc209717fa5ec9f0c94286c` | Registration/v2 and the missing fields are rejected. It has one unresolved node and no build/output from which a carrier can be inferred. | Preserve the v1 sample, add the v3 development shape, and require the media owner to declare exact payload and compliance units when the repository/output exists. |
| **F121 Waydroid development scaffold** | `tools/closure/fixtures/registrations/f121-waydroid.json` at `429504c`, SHA-256 `24d5cb18f25cc7cd935a077d5d2a4414b17f46f85c0701afed494e6c20a5a352` | Registration/v2 and missing v3 fields are rejected. No current fixture artifact binds the Lineage/Waydroid image payloads to their mixed licence/notice carrier. | Preserve the v1 sample, add the v3 development shape, then let the F121 owner split and bind the actual selected image/runtime distribution units. Do not infer one component-wide obligation set. |

### 6.1 Published-copy and documentation consequences

The `021-track-e/f120-handoff` checkout is a copy of the public S120 tree, not a
second contract authority. It will continue to pass the historical v1 command
and must not be edited into a private v2 dialect. Track E must consume a newly
published exact Track H ref when it needs P9 v2.

The research `f120-contracts/` directory and its frozen v1 SHA manifest remain
historical contract evidence. They are not upgraded in place. New schemas,
fixtures and hashes need a new directory/package identity or clearly separated
v2 subtree.

The published S120 declaration remains true for the resolver and staged-
provider mechanism it actually handed off. Ratification does not retract that
history. It does make these claims invalid until requalified on the new line:

- that a v1 lock is the final 0.2.1 release lock;
- that a component licence-array digest proves licence/notice conveyance; or
- that a prefix lacking individually staged readable compliance bytes is
  complete for redistribution.

### 6.2 Work that is not yet a published-consumer break

Track D's `kilix-system-monitor` and Track E's desktop integration commits are
currently recorded as local/unpublished. F111 P5/P6 and F121 final integration
have not published a qualifying consumer. They therefore create migration
work, not a public compatibility incident:

- their product behavior and non-F120 contracts remain intact;
- copied registration/v2 scaffolds and v1 development manifests become
  historical only;
- any final owner fragment must use v3 and supply carrier truth; and
- no current local PASS may be cited as P9 v2 evidence without rerunning on the
  new exact Track H ref.

F105's packaging plan and F100's carrier specification are design consumers,
not published executable F120 consumers. This amendment supplies the missing
F120 join; it does not implement their carrier builders, validators, install
transaction, presentation or retention work.

## 7. Ownership and ordered implementation

If ratified, ownership is:

| Owner | Required work |
| --- | --- |
| Release/F120 contract owner | Freeze exact identity choice and this normative scope; reject any silent v1 edit or strict-profile substitution |
| Track H / F120 | Implement separate parsers, schemas, projection, build-key binding, stage/lock/audit/retirement joins, fixtures and mutation evidence |
| F100 | Freeze and expose the three accepted compliance validators and production carrier authority; implement both installed carrier paths |
| F104/F105 and other stream owners | Supply exact payload descriptors, determinations, licence/notice/modification bytes, A/P and v3 owner fragments |
| Track C / release assembler | Treat each accepted unit as inseparable and carry the complete exact v2 lock/evidence without becoming licence authority |
| Independent reviewers | Review schema/semantic consistency first, then implementation and migrated-consumer evidence |

Ordered gates:

1. owner ratifies this amendment or rejects it explicitly;
2. Track H writes candidate schemas/semantics and goldens without changing v1;
3. independent contract review freezes the exact bytes;
4. F100 supplies accepted validator/API identities;
5. Track H implements and qualifies all §5 mutations;
6. the public pilot and four development families migrate and requalify;
7. stream owners supply final exact carrier units;
8. P9 performs the whole-release v2 run and independent review; and
9. only then may a redistributed artifact be called licence/notice complete in
   the F120 layer.

The contract review and implementation review are separate. A schema can be
internally coherent while the stager still drops the files, which is precisely
the current defect class.

## 8. Owner response form

The owner should copy one line exactly and add identity/date:

```text
F120-C11: RATIFY NEW CONTRACT LINE exactly as proposed in
0.2.1-F120-LICENCE-CARRIER-AMENDMENT.md at SHA-256 <document-sha256>.
```

or:

```text
F120-C11: REJECT NEW CONTRACT LINE; redistributed artifacts remain blocked
pending a replacement owner-ratified mechanism. Frozen v1 is not reinterpreted.
```

No response, a preference without the pinned proposal digest, or permission to
“add the fields to v1” is not ratification. Until a route is ratified and
implemented, F120-C11 remains open and every affected redistributed artifact
remains excluded from P9.

F120 LICENCE CARRIER AMENDMENT PROPOSAL COMPLETE
