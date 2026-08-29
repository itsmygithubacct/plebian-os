# F120 v3/v2/v2 exact-byte independent contract review request

**Status:** R5 AFTER R4 ROOT REJECTION AT 0C/0H/1M/1L; CANDIDATE IS NOT AUTHORITY

Two fresh blind independent reviewers from different model families (`sonnet`
and `kimi`) are requested to review the exact package bound by `SHA256SUMS`.
The R4 pair was genuinely cross-family but does not transfer to changed R5
bytes.  Acceptance must name the SHA-256 of `SHA256SUMS`, the ratified
amendment digest, the candidate HEAD/tree, every command run and every finding.
A review of a later byte sequence does not accept an earlier or later one.

R4 at commit `9f23fc90bbb7d0065295b5e0ce5be214a28fd1fd`, tree
`13c5659fefda3f8d88eb1096f0e77e7806b22fe6`, and candidate-manifest
SHA-256 `a134b759f1795ec58d419487968584e3897365205024de1ab35b43d900daf88c`
was rejected by root adjudication at 0C/0H/1M/1L.  The adjudication records the
R3 High closed and independently confirmed cross-family: 11/11 inherited
finding families re-closed, 7/7 alias documents refused on 3/3 surfaces and
2/2 trusted-gate passes byte-identical.  R5 is a correction, not a re-attempt.
It closes 2/2 open R4 findings and changes nothing else.

**The R4 Low** came from `document_relative_path_errors`: its recursive walk
treated any key named `path`, `staged_path` or `text_path` as a contract path,
including user-named keys in the deliberately open `build_options` scalar map.
R5 scopes that walk **by contract role rather than by key name**: the grammar
now applies only at the 19/19 locations the two published schemas declare a
path field, listed in `CONTRACT_PATH_FIELDS`.  The self-test re-derives that
set from both schemas and refuses on any difference, so the scope cannot drift
away from the schemas it is scoping to.  R5 does not change
`normalized_relative_path`, `valid_relative_path`, either generated schema or
any normalized semantic comparison.

**The R4 Medium** came from the fail-closed envelope covering only the semantic
joins.  Malformed input left three other boundaries as an uncaught traceback:
an unhashable `schema` identity indexed the validator dictionary, nesting past
the interpreter's recursion limit escaped `load_json` (whose `except` clause
did not name `RecursionError`), and the registration parser had no envelope at
all.  R5 extends the envelope over the registration parser, the schema pass and
the path walk; converts nesting depth into `F120-V2-LOAD`; and compares schema
identity instead of using it as a dictionary or set key.  No refusal family is
added, and no previously refused document is now accepted.

Fresh reviewers must verify, on their own bytes: 6/6 opaque build-option
controls (3/3 key names across 2/2 workspace/release documents) are accepted
after exact build-key rebinding; 7/7 real contract path fields still refuse the
same alias with `F120-V2-PATH`; and 4/4 malformed shapes -- unhashable identity
in both modes, deep nesting in both modes, and both registration aborts --
return a named profile family with no traceback.

R3 at commit `f8878ec7124acd2224cadbdde319c6f34f8724a7`, tree
`a12a14cd3e26f200313fb2390b14ef87f93a00c0`, and candidate-manifest
SHA-256 `76e4e501a8e276fda3877ca7a3298ea3bc1608ab43bec382b83537b85a655aad`
was rejected by root adjudication.  Review 1 accepted at zero findings; Review
2 returned 0C/1H/0M/2L.  The adjudication upholds all eight R2 return
conditions as closed.  No R3 or R4 review transfers to R5.

The decisive R3 High accepted an internally re-bound release lock whose payload
artifact used `share//licenses/demo/Apache-2.0.txt` or
`share/./licenses/demo/Apache-2.0.txt` while its own unit's readable licence
used `share/licenses/demo/Apache-2.0.txt`; the string-distinct spellings name
one filesystem file but bypassed raw-string uniqueness.  The corrected
adjudication and cross-family reproduction explicitly distinguish this from the
already-refused string-exact control.  R5 retains R4's acceptance fix, rather than
adding a diagnostic to an accepted document, by:

- retaining the frozen normalized POSIX relative-path grammar in registration
  v3 and both generated schemas, while independently normalizing safe relative
  paths before artifact uniqueness, staged-artifact, notice-union and
  copy-closure comparisons;
- adding a canonical self-consistent fixture that rebinds the unit digest and
  payload binding after constructing the `share//...` payload/licence alias,
  and requiring both `F120-V2-PATH` and
  `F120-V2-DUPLICATE-ARTIFACT-PATH` under preflight, qualification and direct
  release joins for both `share//...` and `share/./...` spellings;
- requiring exactly one validation mode at the public library boundary as well
  as the CLI boundary; and
- converting malformed semantic/census aborts into stable named refusals while
  preserving the semantic names already paired with schema-invalid fixtures.

R2 at commit `c995a21d7b743564556b0cd1f65e123b75532e34`, tree
`28d8eb18cd5d9dbada1278a4107a332ff10e17e8`, and candidate-manifest SHA-256
`c4b57ccb91ce238c453dac4991c5cdc21316c261437c188b3ca8910be0f6320b`
was rejected by root adjudication.  Review 1's incomplete no-finding return was
not an acceptance; Review 2 returned 0C/0H/4M/4L.  R5 retains R3's closure of
those eight adjudicated return conditions:

- binding `--release-qualification` to an exact release-lock/v2 input and
  making it exclusive with `--self-test` and `--write-hashes`;
- retaining the closed registration/v2 dependency, enum, toolchain, build,
  environment and array rules in the registration/v3 successor;
- refusing non-canonical input bytes before schema or semantic joins;
- carrying the frozen graph ordering and same-process native-provider
  revision-conflict rules into workspace/release v2;
- rejecting all-zero artifact/digest placeholders;
- enforcing non-empty and per-unit registration bounds;
- rejecting fractional build-option values in the parser and both schemas;
  and
- expressing declaration-only roles, compatible kind/role pairs, and exactly
  one conveyance notice directly in Draft 2020-12 schemas.

All thirteen inherited finding closures (8/8 R2, 3/3 R3 and 2/2 R4) are claims for fresh reviewers to
reproduce, not findings closed by this request.  Nothing here carries any
earlier review to the changed bytes.

## Contract-review scope

Each reviewer must independently establish:

1. `RATIFIED-AMENDMENT.md` hashes to
   `0e1d8ca1fd330bd47a836ad4f221b1df4e04b670c7af259296d2e90238be039e`;
2. frozen `../contracts/` v1 bytes are untouched and still pass their own gate;
3. the four candidate identities and strict incompatibility rules match the
   ratified text;
4. both schemas pass Draft 2020-12 meta-validation and encode every rule that
   JSON Schema can express with closed object shapes;
5. the registration parser is closed and refuses both reserved build options,
   guessed carriers, declared internal stage manifests and every non-normalized
   relative-path spelling refused by frozen registration/v2;
6. the exact expanded-unit profile is unambiguous about source versus staged
   paths and contains every referenced artifact's identity, path and digest;
7. the component union is not treated as the per-payload obligation answer;
8. payload, shared and exclusive compliance coverage matches §§3.4 and 3.8,
   including path uniqueness over normalized comparison keys independently of
   canonical-path syntax refusal;
9. A, P, licence, notice, build-key and compliance-unit digests have one
   canonical computation and no self-reference;
10. no CLI or library release path can use `--contract-preflight`, omit its
    mode or bypass absent F100 validator authority;
11. two differently obligated units and one uniform multi-payload unit are
    represented in valid registration/workspace/release goldens; and
12. the original zero-notice shape produces the exact named refusal
    `F120-V2-ZERO-NOTICE-CARRIER`;
13. all 23 refusal families fixed by `PROFILE.md` have a focused generated
    fixture or, for absent F100, an explicit qualification-mode assertion; and
14. recursive package census refuses added root files and nested fixture bytes,
    while the explicit preflight/qualification modes cannot return a successful
    qualification result when F100 is absent;
15. both self-consistent `share//...` and `share/./...` payload/licence aliases
    produce `F120-V2-DUPLICATE-ARTIFACT-PATH` under preflight, qualification
    and direct joins, while the string-exact control remains refused by the same
    name and qualification does not emit only the temporary
    F100-validator-unavailable condition;
16. malformed release toolchain/path shapes and a missing manifest-bound member
    return stable named refusals without a traceback; and
17. all 24 invalid fixtures reach their independently enumerated primary names.
18. scalar `build_options` keys named `path`, `staged_path` and `text_path` are
    accepted in both 2/2 workspace/release documents, including non-normalized-
    looking values and exact release build-key rebinding, while actual contract
    path fields retain the normalized grammar and alias refusals; and
19. no input at the public library boundary leaves as an uncaught exception:
    an unhashable schema identity, a document nested past the interpreter's
    recursion limit, and a malformed registration document each return a
    stable named refusal from the 23 profile families.

The candidate self-test must additionally replay all 8/8 R2, 3/3 R3 and 2/2 R4
adjudication counterexample families.  Reviewers must independently mutate them
again; candidate-authored regression controls are evidence, not independent
closure.

## Explicitly not yet claimable

This contract review does not close implementation acceptance.  F100 has not
yet returned accepted validator/API identities, and the current candidate
therefore correctly refuses normal release qualification.  The F104 CAM++ and
F105 exact carrier positives, all byte-level F100 joins, staged-prefix
regular/no-follow/readability checks, selection/retirement barriers,
crash/concurrency campaign and migrated-consumer qualification remain later
gates.  A reviewer must not convert their absence into a contract pass or
silently substitute a local validator.

## Required commands

Build an external F120 launcher bundle from the exact independent checkout and
invoke its `check` transaction.  That transaction now runs frozen v1, this
candidate self-test and the resolver tests as three isolated children only
after the external closure gate:

```sh
/external/review-bundle/f120-authority \
  --subject /exact/checkout/tools/closure check
```

Also run the non-authorizing deterministic construction checks:

```sh
uv run --locked python build_candidate.py --check
uv lock --check
sha256sum -c SHA256SUMS
```

The direct `uv` command is not accepted evidence for validator execution; only
the external launcher's candidate child is.  Compare frozen v1's complete
package hashes with its accepted identity.  Repeat the complete external and
construction commands without modifying any package byte and report whether
the package and output hashes remain identical.
