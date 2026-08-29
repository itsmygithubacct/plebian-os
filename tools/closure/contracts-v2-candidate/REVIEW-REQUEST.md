# F120 v3/v2/v2 exact-byte independent contract review request

**Status:** R3 AFTER ROOT REJECTION AT 0C/0H/4M/4L; CANDIDATE IS NOT AUTHORITY

Two independent reviewers are requested to review the exact package bound by
`SHA256SUMS`.  Acceptance must name the SHA-256 of `SHA256SUMS`, the ratified
amendment digest, the candidate HEAD/tree, every command run and every finding.
A review of a later byte sequence does not accept an earlier or later one.

R2 at commit `c995a21d7b743564556b0cd1f65e123b75532e34`, tree
`28d8eb18cd5d9dbada1278a4107a332ff10e17e8`, and candidate-manifest SHA-256
`c4b57ccb91ce238c453dac4991c5cdc21316c261437c188b3ca8910be0f6320b`
was rejected by root adjudication.  Review 1's incomplete no-finding return was
not an acceptance; Review 2 returned 0C/0H/4M/4L.  This R3 round claims only
that it closes the eight adjudicated return conditions by:

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

Those are claims for fresh reviewers to reproduce, not findings closed by this
request.  Nothing here carries either earlier review to the changed bytes.

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
   guessed carriers and declared internal stage manifests;
6. the exact expanded-unit profile is unambiguous about source versus staged
   paths and contains every referenced artifact's identity, path and digest;
7. the component union is not treated as the per-payload obligation answer;
8. payload, shared and exclusive compliance coverage matches §§3.4 and 3.8;
9. A, P, licence, notice, build-key and compliance-unit digests have one
   canonical computation and no self-reference;
10. no normal release path can use `--contract-preflight` or bypass absent F100
    validator authority;
11. two differently obligated units and one uniform multi-payload unit are
    represented in valid registration/workspace/release goldens; and
12. the original zero-notice shape produces the exact named refusal
    `F120-V2-ZERO-NOTICE-CARRIER`;
13. all 20 refusal families fixed by `PROFILE.md` have a focused generated
    fixture or, for absent F100, an explicit qualification-mode assertion; and
14. recursive package census refuses added root files and nested fixture bytes,
    while the explicit preflight/qualification modes cannot return a successful
    qualification result when F100 is absent.

The candidate self-test must additionally replay all eight R2 adjudication
counterexample families.  Reviewers must independently mutate them again;
candidate-authored regression controls are evidence, not independent closure.

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
