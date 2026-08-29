# F120 v3/v2/v2 exact-byte independent contract review request

**Status:** R4 AFTER R3 ROOT REJECTION AT 0C/1H/0M/2L; CANDIDATE IS NOT AUTHORITY

Two fresh blind independent reviewers from different model families are
requested to review the exact package bound by `SHA256SUMS`.  The two R3 seats
were separate sessions but not different model families, so they do not satisfy
this structural requirement.  Acceptance must name the SHA-256 of `SHA256SUMS`, the ratified
amendment digest, the candidate HEAD/tree, every command run and every finding.
A review of a later byte sequence does not accept an earlier or later one.

R3 at commit `f8878ec7124acd2224cadbdde319c6f34f8724a7`, tree
`a12a14cd3e26f200313fb2390b14ef87f93a00c0`, and candidate-manifest
SHA-256 `76e4e501a8e276fda3877ca7a3298ea3bc1608ab43bec382b83537b85a655aad`
was rejected by root adjudication.  Review 1 accepted at zero findings; Review
2 returned 0C/1H/0M/2L.  The adjudication upholds all eight R2 return
conditions as closed.  No R3 review transfers to R4.

The decisive R3 High accepted an internally re-bound release lock whose payload
artifact used `./share/licenses/...` while its own unit's readable licence used
`share/licenses/...`; the two strings named one staged file but bypassed raw
string uniqueness.  R4 fixes the acceptance, rather than adding a diagnostic to
an accepted document, by:

- retaining the frozen normalized POSIX relative-path grammar in registration
  v3, both generated schemas and the release semantic joins;
- adding a canonical self-consistent fixture that rebinds the unit digest and
  payload binding after constructing the payload/licence alias, and requiring
  `F120-V2-PATH` under preflight, qualification and direct release joins;
- requiring exactly one validation mode at the public library boundary as well
  as the CLI boundary; and
- converting malformed semantic/census aborts into stable named refusals while
  preserving the semantic names already paired with schema-invalid fixtures.

R2 at commit `c995a21d7b743564556b0cd1f65e123b75532e34`, tree
`28d8eb18cd5d9dbada1278a4107a332ff10e17e8`, and candidate-manifest SHA-256
`c4b57ccb91ce238c453dac4991c5cdc21316c261437c188b3ca8910be0f6320b`
was rejected by root adjudication.  Review 1's incomplete no-finding return was
not an acceptance; Review 2 returned 0C/0H/4M/4L.  R4 retains R3's closure of
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

All eleven inherited finding closures are claims for fresh reviewers to
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
   including path uniqueness after normalized-path enforcement;
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
15. the self-consistent payload/licence path-alias fixture produces a real
    F120-owned path refusal under preflight and qualification, rather than only
    the temporary F100-validator-unavailable condition;
16. malformed release toolchain/path shapes and a missing manifest-bound member
    return stable named refusals without a traceback; and
17. all 24 invalid fixtures reach their independently enumerated primary names.

The candidate self-test must additionally replay all eight R2 and all three R3
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
