# Independent seat 1 — recovered RC2 carrier and F107-A merge

Reviewed commit: `bb2466a9b6fe23f6bd6363f7fafb030bb61076be`.
Integration base: `a3afc6380d7ff08326762720ac880797c5bbb256`.

I did not author this carrier or the F107-A merge.

The complete carrier and merge were reviewed against OD-BA obligations 1–5, OD-BB, OD-BC, F100-CARRIER-DESIGN §§5–7, M0-OS-IMPL §5, the J1/J2 ruling, and the earlier carrier seat reports. The verdict covers this implementation and its generated pre-seat artifact. It does not certify a published image or waive the need to attach the two actual accepting reviews, generate the real receipt and pin its digest. The reviewed commit intentionally lacks that receipt and correctly refuses the build guard.

## Findings

### Low — original owner determinations still require an external review comparison

`build/generate-model-compliance.py:248-255` requires determination inputs but copies their bytes without checking an independently recorded approved digest. `tests/test_model_compliance_carrier.py:89-90` regenerates from the vendored copies; `tests/test_model_compliance_carrier.py:391-403` checks their internal hashes, model coverage and owner marker. This is the residual determination-authenticity limitation identified by the earlier seat 2 report.

Concrete independent probe: in a private copy, I replaced the lgraph determination's licence classification with `FORGED-LICENCE-FOR-NEGATIVE-CONTROL`, retained its owner marker, regenerated the artifact and synthetic receipt, and changed both private release pins to match. All 13 carrier tests passed. A future reviewer who treats those tests as proof of owner authorization could therefore accept substituted determination text. Record approved determination digests independently and have generation reject other inputs, or retain an explicit original-record comparison as a mandatory review step.

This is not an unchanged-pin bypass: changing the determination changes the bound artifact and its reviewed release pin. For this exact candidate I independently compared all four vendored determinations with their original research records, found byte equality, and regenerated from those originals. The current artifact is authentic; the remaining issue is reliance on that external review step.

No unresolved High or Medium finding was identified.

## Independent evidence and earlier-finding disposition

- **Pinned trust chain fixed.** `build/remaster-iso.sh:275-302` binds `CARRIER.json` to the release pin, then `BINDINGS.sha256` to that JSON, then all generated evidence to the bindings. In private completed copies, changing the licensor projection or NOTICE and recomputing only `SHA256SUMS` refused at the bound-file check. Both release pins remained unchanged.
- **Missing and forged seats fixed.** `build/remaster-iso.sh:303-335` enumerates the seat paths in the pinned receipt, checks each file and digest, requires at least two, and rejects extra unbound files. Deleting one named seat, deleting the whole seat directory, or changing a seat's bytes and recomputing only `SHA256SUMS` each refused at the named-seat check. An extra forged seat refused as unbound. Replacing the receipt refused at its digest check; removing it refused as missing. The honest private synthetic two-seat fixture returned zero with empty stderr. Synthetic fixtures were clearly labelled and never placed in the candidate.
- **Independent generation.** Regeneration from the original research-record determinations and the release-pinned content and licence trees reproduced all 28 pre-seat files byte-for-byte. The resulting `CARRIER.json` digest is `b149897e7cd1d78f01cb89bb5218d9f420a99c2040ad28d36c81bc4e444d0ca3`, matching both release pin files. The asset records served by the pinned host's content gitlink equal the carried records; the added test closes the earlier untested gitlink-drift risk.
- **Delivery claims and both download gates fixed.** DELIVERY now describes a download gate, not a runtime-use gate. Provisioning keeps model weights disabled. At `KILIX_REF=4e5b548167a7688df8e267fcc46f515a2648c77f`, `scripts/install-kilix-voice.sh` calls `require_dictation_receipt` for the selected model before fetching its archive; missing receipt exits 3. That host pins Bonsai `32e99fa974a8d12c701fe90d408c45b6f0efa046`, whose common `models/_shared/pull.sh` asks the declared model's licence gate before downloading. I ran the pinned voice installer suite (45 tests, all passed) and pinned Bonsai script suite (22 tests, all passed), including no-receipt/no-download controls and a positive simulated checker control. No real licence was accepted and no model weights were downloaded.
- **Design deviations remain sound.** Covering three advertised models is required by completeness. Multiple licences, licensors and texts preserve the VibeVoice and decoder-lineage obligations; that model remains advertised as installable but not runnable. Keeping the receipt digest outside `CARRIER.json` avoids a digest cycle: the separately pinned receipt binds the carrier digest and exact seat bytes. Vendoring the determinations makes review reproducible, subject to the Low finding above.
- **F107-A obligations preserved.** The no-carrier arms retain the exact refusal line and no extra stderr. A named invalid carrier adds the design's diagnostic before that unchanged line. The real pre-seat candidate refuses because the receipt pin is missing. The dated-heading RC-9 test body is unchanged from the integration base; F107-A's rewrite was not adopted. `releases/0.2.1.env` and `releases/0.2.1-notes.md` are byte-identical to the base. The CHANGELOG's 0.2.1 history is preserved and UPGRADING correctly dates split closures to 0.2.2.
- **Selector reconciliation preserved.** The exact development-commit and bare-source lanes remain in `provision/plebian-os-select-closure.sh:697-733`; the trusted tag-object anchor is confined to the release arm at line 735 onward. The publication gate excludes development selections at line 861 while preserving their component-history checks. Native-runtime closure validation remains at lines 429 and 482. The selector tests cover these lanes, malformed targets, offline trust and preservation on failed transactions.
- **Newer RC2 work preserved.** The host pin is a descendant of base host `10dfa8100fa6333280b3ee3f94e27c1474a4ac0a`; the desktop pin `6dbb7b90bda9f8cdfb91fea3337a9517c00b0f6f` is a descendant of base desktop `838a79b1d72d95bf4e9413ec9b013ca2f09e5bb9`. The recovery therefore retains the newer camera, chrome, battery and routing ancestry instead of reverting those pins to the earlier carrier line. Other existing release pin values are unchanged.

## Validation scope

All execution used private copies under `env -i`, private HOME, TMPDIR and XDG directories, and explicit read-only source-repository variables. Unittest discovery used `-s tests` without `-t .`. The candidate and source repositories were not edited. No image was built or published.

The untouched pre-seat copy ran 883 tests: 1 failure, 29 errors and 2 skips. Every failure/error was confined to the receipt-dependent carrier methods AC-4, AC-6, AC-7 and AC-9 through AC-12, including their subtests, and arose from the deliberately absent receipt, seats or receipt pin. Every non-carrier test passed. The completed private-copy full suite ran 883 tests and passed, with 2 skips. A separate focused run passed all 13 carrier tests, including the expanded planted-defect battery and delivery/catalog controls. Shell syntax, Python compilation and shell lint at warning severity passed.

VERDICT: ship with known issues
