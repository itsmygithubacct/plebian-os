# Independent seat 2 — recovered RC2 carrier and F107-A merge

Reviewed commit: `bb2466a9b6fe23f6bd6363f7fafb030bb61076be`.
Release-line comparison base: `a3afc6380d7ff08326762720ac880797c5bbb256`.

I did not author this carrier or the F107-A merge.

The review covers the complete carrier and merge against OD-BA obligations 1–5, OD-BB, OD-BC, F100-CARRIER-DESIGN sections 5–7, M0-OS-IMPL section 5, and the J1/J2 ruling. I read both original carrier seat reports and the subsequent seat-1 report. Source repositories and the candidate were read-only. Mutation probes used private copies, a sterile environment, private HOME/TMPDIR/XDG directories, and explicit object-store locations for the five required source repositories.

## Findings

### Low — determination authenticity still depends on independent source comparison

`build/generate-model-compliance.py:248-255` copies the supplied determination bytes without comparing them with an independently recorded expected digest. `tests/test_model_compliance_carrier.py:85-94` regenerates from the vendored determinations, and `tests/test_model_compliance_carrier.py:391-403` checks their internal receipt hashes and owner marker. This remains the earlier seat-2 L1 limitation and does not implement the generator refusal described in design section 5.3.

Concrete probe: I appended labelled substitute bytes to a private copy of the lgraph determination. The generator accepted and bound that changed file. A future maintainer could consistently regenerate and re-pin a substituted determination without those checks authenticating its origin. The release diff and independent comparison with the original research record remain necessary. This is not an unchanged-pin bypass: bound-file verification rejects changing a determination after it is pinned.

For this exact candidate I performed that independent comparison: all four vendored determination files equal their research originals byte-for-byte, and regeneration from those originals reproduces the complete committed carrier. Consequently this limitation does not leave a false determination in the reviewed artifact. No High or Medium finding remains.

## Independent evidence

### Generation, records and receipts

I ran `build/generate-model-compliance.py` against the exact release-pinned content and licence trees, supplying the original research determinations rather than the vendored copies. All **28 files** reproduced byte-for-byte. The generated `CARRIER.json` digest is `b149897e7cd1d78f01cb89bb5218d9f420a99c2040ad28d36c81bc4e444d0ca3`, matching both release declarations.

The four original determination digests are:

| Record | SHA-256 |
| --- | --- |
| small-en-us | `b6a44eca20a27c550b7fe1cf8e83e384f5ead0c2086130d24dd7684c1a536263` |
| lgraph-en-us | `109fc3ad04b0bd7d76c00e8987a7bdbdc81e7dac389b4c3c46f7eea8b3ecdecf` |
| vibevoice-asr-bitnet | `889658d7317c30f3fc8cdd1780f961feaeb9017573dccdfc552185967228bd33` |
| J1/J2 ruling | `3618c282d871e8333b53aec18561658fb2a9d94b91dd9861358c901cbff6dcf9` |

The asset records, member-manifest bindings, licence records, record digests and digest-addressed texts are derived through the pinned implementations. The new served-record check also proves that all three carried asset records equal those served by the content gitlink of the pinned host, closing the earlier seat-2 M2 gap.

The three-model set is required by the advertised catalog. The dual-licence VibeVoice entry includes both licensors and texts, and declares the model installable but not runnable. The separately pinned build-acceptance receipt is a sound way to avoid a digest cycle; its schema remains distinct from a user's licence receipt. Vendoring determinations is sound, subject to the Low finding above. No user licence receipt was created or shipped by these probes.

### Build gate and earlier trust failures

The actual candidate intentionally has no acceptance receipt, seat files or receipt pin. Running its release guard with the actual manifest refuses with `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256 is not a sha256`, followed by the unchanged F107-A refusal line. This is the required fail-closed state before acceptance.

In a private copy only, I generated two distinct, conspicuously labelled synthetic seat fixtures and their receipt, then added the receipt pin. They are test inputs, not independent approvals, and are absent from the candidate. This completed-copy positive control returned zero with empty stderr. With the same release inputs, the baseline validator also returned zero with empty stderr; the merged validator with no carrier returned one and exactly the original refusal line. This independently reproduces the required baseline/present/absent control.

With both pins unchanged, each independent mutation below returned refusal at its relevant check:

| Mutation | Observed refusal |
| --- | --- |
| Fictitious lgraph licensor in projection and notice; regenerate only `SHA256SUMS` | Bound file does not match `BINDINGS.sha256` |
| Delete one receipt-named seat; regenerate checksums | Named seat missing or not the record the receipt names |
| Delete the entire seats directory; regenerate checksums | Named seat missing or not the record the receipt names |
| Add an extra file and include it in checksums | File bound by neither pin |
| Replace a named seat with a symlink | Named seat missing or not the record the receipt names |
| Replace `CARRIER.env` with a symlink | Projection missing or not a regular file |

The pinned carrier now binds `BINDINGS.sha256`, which binds the generated evidence and shell projection. The pinned receipt's named seats are enumerated and required to exist with matching bytes. The earlier bound-file and missing-seat High findings are therefore closed. The completed-copy carrier tests also exercise the full planted-defect battery, including D4b, D5b, D6 and D9; the latter two distinguish interface/delivery evidence from what a self-consistently re-pinned shell input alone can establish.

### Delivery and pinned download gates

`provision/plebian-os-provision.sh` fixes `PROVISION_VOICE_WEIGHTS=0`; the corrected delivery text makes an installation/download claim and no longer falsely claims a runtime use gate. The pinned content first-use route and speech install action retain their receipt checks.

At host commit `4e5b548167a7688df8e267fcc46f515a2648c77f`, `scripts/install-kilix-voice.sh:1039` calls `require_dictation_receipt` immediately before the model fetch at line 1041. I extracted the exact gate function and probed both small-en-us and lgraph-en-us with checker statuses 0, 3, 1 and 127. Only zero reached the fetch marker; every call named the selected model. Missing coverage returned 3, and checker failures refused. Source inspection confirms the existing verified-model fast path does not fetch new weights.

That host pins Bonsai `32e99fa974a8d12c701fe90d408c45b6f0efa046`. I ran its six licence-gate tests from an extracted private tree with network commands replaced by markers. No receipt, no checker, `--force`, and local-copy installation all refused before download; the positive checker control reached the download marker; dry-run fetched nothing. The model's `licence_gate`, plan output and shared pull script carry the gate across the advertised routes. This closes the earlier ungated direct voice and Bonsai routes without accepting a licence or downloading weights during review.

### Merge and regression obligations

- `releases/0.2.1.env` and `releases/0.2.1-notes.md` are byte-identical to the release-line base. The earlier CHANGELOG regression is removed, and `UPGRADING.md:56` correctly introduces split closures at 0.2.2.
- The RC-9 dated-heading assertion is retained; the F107-A rewrite is absent. The baseline already supplies the dated heading.
- No-carrier controls preserve byte-identical refusal stderr. Named invalid carriers add the design's diagnostic and retain the same final refusal line.
- The closure-selection suite covers the retained development lane, release-only trusted-tag/publication checks, native-runtime validation and split layout. The 0.2.2 selector behavior survives the merge.
- The selected host is a descendant of baseline host `10dfa8100fa6333280b3ee3f94e27c1474a4ac0a`. Its intervening changes add the speech gates, dependency pin and test adjustments; they do not replace the newer camera, chrome, battery or routing implementation. Desktop `6dbb7b90bda9f8cdfb91fea3337a9517c00b0f6f` descends from baseline `838a79b1d72d95bf4e9413ec9b013ca2f09e5bb9`, with only its CI pairing changed. Other existing release pins are preserved.

## Validation and scope

I completed separate stable-copy runs using `python3 -m unittest discover -s tests` without `-t .`:

- **Pristine candidate:** 883 tests; one failure, 29 error instances, two skips. Every failure/error is in receipt-dependent carrier checks: AC-4, AC-6, AC-7, AC-9, AC-10, AC-11 and AC-12. They are missing-receipt or missing-pin fixture failures, including AC-11 subtests. All other tests pass. The direct real-candidate guard probe independently establishes the expected refusal.
- **Private copy completed with synthetic seats and receipt:** 883 tests; all pass, two skips. A separate focused run passes all 13 carrier test methods. Synthetic success demonstrates the interface and guards, not actual independent acceptance.
- **Other CI checks:** shell syntax checks, Python compilation and warning-level shell lint all pass. The separate authority-profile suite passes all six tests.

The final candidate status is clean. These runs did not modify the candidate, source stores or live model data.

This verdict approves the reviewed carrier implementation and F107-A integration with the Low issue recorded above. It does not claim that this intentionally incomplete commit already contains an accepted receipt, nor authorize treating the old rejecting reports or synthetic fixtures as acceptance. The real receipt must name the two actual approving reviews, be pinned, and pass the completed-artifact checks. No ISO build, runtime hardware qualification, publication or model acceptance was performed.

VERDICT: ship with known issues
