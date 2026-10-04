**Independent seat 2: RC5 workflow Content and model-carrier rebinding**

Reviewed 2026-10-04. I did not author the implementation. I independently
inspected the selected source, compared Git objects and carrier bytes, and ran
the checks described here. I did not inspect or consult the other fresh
reviewer's record. The previous seat 2 record was read with `git show` from the
OS base solely for historical context; it provides no approval for this change.

I found no blocking defect in the exact Content rebinding, source selections,
or unchanged model-compliance payload reviewed here. This is a conditional
source-integration verdict. The provisional carrier deliberately lacks an
acceptance receipt and seats; integration remains conditional on the final
steps below.

| Reviewed input | Exact value |
| --- | --- |
| OS source base | `d2ec9a94db375249562d2dbbc355a3e03fca309d` |
| Provisional `CARRIER.json` SHA-256 | `dff5ce2201ad01d52e50320033658910d2a89529d4afc2a1dd09bccca0c162d3` |
| `BINDINGS.sha256` SHA-256 | `38a445cf4dfa7195f52c2d0f2cc2d91132f947c0c9fc73fba2b377ecd706abc7` |
| Selected Content | `21c6f503ea3a9e5a094724f572a2310ea5ad55ba` |
| Previous Content | `b7833f3f2986b1c5423898a2130bf345f04f568b` |
| Host | `a086ff2241ef36549ea5fddd583baf85de8d34b0` |
| Needle | `f566595d296b6f9d556352b7120866af8acb40fd` |
| TUI utilities | `75ce46b57ea45262fd56f87766b24ed6100b0449` |
| Licence authority | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` |
| Voice source, unchanged | `a12be47e289ca03fccd46840276add1833df5760` |
| Host-selected Bonsai source, unchanged | `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685` |
| Content catalogue SHA-256 | `731120ad2088bd9cd9191a8f1280fe58ee61055a9d11cca87dee95ca6e3b0ead` |
| Asset/v3 schema SHA-256, unchanged | `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870` |

The four component worktrees were clean and their commit/tree identities
matched the supplied source manifest. The OS review covers its uncommitted
release-file changes above the stated base. I inspected `REVIEW.json`,
`PLAN.json`, `CHECKS.json`, and `source-manifest.json` as candidate context,
then checked the claims against source and my own executions.

Independent catalogue comparison finds exactly two semantic changes:
`/content/47/source/ref` selects Needle and `/packages/0/source/ref` selects
the TUI utilities above. All 32 asset mappings are unchanged. The actual
catalogue bytes hash to the updated production trust pin in `receipt.py`;
the asset schema and its pin are unchanged. The Content commit changes only
those selections, the catalogue digest, and two selection-test expectations.
All 139 vendored Licence files retain their modes and blob identities and
match their counterparts in the exact selected Licence Git tree.

The host's actual `third_party/kilix-content` gitlink selects the reviewed
Content commit. Its Qwen `CONTENT_REF` selects that same commit and retains
the Licence authority above. The actual-checkout authority regression passes;
a separate control temporarily substituting the previous Content constant
refuses the current clean checkout with the expected authority error. The
Content TUI package, host installer default, and Needle's TUI gitlink all
select exactly `75ce46b57ea45262fd56f87766b24ed6100b0449`.

The provisional carrier has 37 regular files and matches the OS worktree's
carrier byte for byte. Independent hashing verifies 34 unique binding entries
and 36 unique checksum entries, their complete expected file populations,
and the binding digest in `CARRIER.json`. Compared with the carrier stored in
the OS base, all 33 model artifact, licence record, notice, delivery, licence
text, and determination/ruling files are byte-identical. The JSON changes
only `interface_content_ref` and `bindings_sha256`; its environment changes
only `interface_content_ref`. The six determination/ruling files, four models,
model order, runnability declarations, source/download identities, digests,
licensors, decisions, and first-use delivery modes are unchanged.

The generator reads the exact selected Git archives rather than the repositories'
current working-tree contents. Regeneration with the selected Content and
Licence objects, all six original determination/ruling files, and no seats
passes `--check` against the provisional carrier. The generator, release
guard, and provisioner are unchanged from the OS base. The host's voice and
Bonsai installers and Qwen generation launcher are unchanged from its
integration base `1e21cfd8b9248ea4251a906c0ae71329abfae699`.

I read `build/remaster-iso.sh`, `build/generate-model-compliance.py`,
`tests/test_model_compliance_carrier.py`, and the relevant voice-contract
probes. The guard requires a receipt bound to the carrier, verifies bound
files and seat digests, refuses unbound files, checks interface/release pins,
and reads the selected host's complete Content gitlink. Its acceptance does
not independently establish reviewer independence or legal correctness;
the actual review process, exact-source comparisons, and acceptance suite
remain necessary. No guard or test was weakened for this review.

Executed checks, with the selected source paths explicitly supplied where
the suites require sibling repositories:

- Content `make check`: 314 tests pass, followed by
  `tools/generate_upstream_records.py --check` passing.
- Carrier generator `--check`, independent Git/catalogue/file comparisons,
  and `sha256sum --check --strict` for both carrier checksum lists pass.
- OS `python3 -m unittest -v` runs seven carrier checks covering regeneration,
  projection, Licence-source equality, served asset records, model coverage,
  delivery gates, and absent-carrier refusal, plus `test_dependency_manifest`
  and `test_release_versioning`: 77 tests pass without skips.
- Host `test_qwen_provider_route.QwenProviderRouteTests.test_selected_host_content_passes_provider_authority_check`
  passes. The additional stale-authority refusal control also passes.
- TUI `test_rollout_child_status` and `test_rollout_resume`: 107 tests pass
  without skips, including a private tmux startup/early-exit fixture. An
  additional mocked batch control verifies that a child failure after tmux
  creation preserves its failure result and applies the full 2.5-second
  delay before the next launch.
- Needle `test_files`, `test_files_visibility`,
  `test_observed_cli_regressions`, and `test_tmux`: 74 tests pass without
  skips. The explicit private-test backend loads the selected host's actual
  `config/kilix_tmux` source through a disposable CLI wrapper. The tests check
  prefix/visibility filtering, literal UTF-8 and mixed quotes, trailing
  semicolons, file/stdin transport, consent, and separate Enter submission.
- Host `test_tmux_control`, `test_tmux_literal_input`, and
  `test_tmux_cli_help`: 13 tests pass without skips. OS `git diff --check`
  also passes.

The real release guard, invoked against this provisional carrier and its
release pins, returns 1 with `ACCEPTANCE.json is missing or not a regular file`
and the required release-mode refusal. I created no substitute receipt or
approval records to obtain a passing guard. Receipt-dependent positive,
tamper, full-gitlink, and final pin tests are pending the real final receipt;
the counts above do not represent a complete carrier acceptance run.

Before integration, the coordinator must:

1. Obtain the other genuine independent review of these exact inputs and
   resolve any blocking findings.
2. Generate the final carrier with both actual fresh records, retaining this
   `CARRIER.json` digest and unchanged model payload. Bind the generated
   `ACCEPTANCE.json` digest in both `releases/0.2.2.env` and
   `releases/0.2.2.requirements`, alongside the matching carrier and interface
   pins. The historical receipt digest currently left in those files is
   pending replacement and does not approve this carrier.
3. Verify byte-identical final regeneration, both actual seat digests and
   determination bindings, and run the complete carrier acceptance and
   final closure/source-pin checks on the final bound state. Publication
   hygiene and remote source-ref verification remain required.

This review preserves existing owner determinations and grants no new model
rights or user consent. It does not qualify live providers, model inference,
installed runtimes, hosted CI, hardware behavior, an ISO, or upgrade/release
acceptance, and it closes none of those separate gates. No product source,
allowlist, or commit was edited or published by this reviewer. Private
supporting commands and results are retained with evidence run
`workflow-integration-20261004/review-seats/seat2`.

VERDICT: ship
