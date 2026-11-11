# Seat A: RC8 carrier and follow-up source review

VERDICT: ship with known issues

This verdict accepts the model-compliance carrier identified below for inclusion in the RC8 candidate. It does not qualify an installer image, approve publication of an untested release, or assert that the final assembled release closure has passed acceptance.

I did not author the reviewed implementation, content pin, model records, carrier generator, or carrier. I independently inspected the changes, exercised the sources, and wrote this report. I did not read the other seat's report. I identified the plain-close descendant defect and the Debian package downgrade issue during review; the builder implemented the fixes, which I then checked.

## Exact carrier and source scope

- Carrier SHA-256: `62d0c8007feff7718dc8ccc1180f2256ca7dfaa53e52755e2a9297115e314630`.
- Default-model archive SHA-256: `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.
- Content interface: `db463a7b32acac83d28b9ab8a1dce183e14931b2`.
- Licence interface: `596ada2ab68b9ec441674ff4da2d431559d47378`.
- Voice: `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`.
- PDF Conversion: `873f3298cfe9bcbf295061cd35d5054a46f4b21a`.
- Pleb Go follow-up: `8efc38b6799624cf8a979be1a49bb5f710f9e5a8`.
- PTY broker follow-up: `5ec6fb7aacb8e8f7a24b0e600616c5570c153f16`.
- Initial reviewed OS source: `749af82241bce3daa77bdccea155f45e02bc280b`, including the Debian provider change in `73d998fe1ea63fac5e3c9d6101b67328f8cf2a43`.
- Initial pane UI source: Kitty `35730d17fd74c664a062bb0742cf5756ae221f1a`, integrated by Kilix `dd4d8eda3818265f3df0bfb1ef5379913fdc3f57`.

The carrier was reviewed before its new two-seat receipt existed. Final host pins and documentation were still being assembled. This report binds the carrier digest and named source commits, not an unspecified later OS commit.

## Carrier findings and checks

The content change updates the PDF application ref and the packaged catalog digest. It changes no model asset records. Comparing the carrier with the previous OS carrier found changes only in `interface_content_ref` and `bindings_sha256`; model entries and their delivery modes remain unchanged. Determination and licence-text files are byte-identical to the prior carrier. This pin update therefore introduces no new model distribution determination.

Independent tests passed:

- Byte-identical regeneration of the carrier with its actual determinations and no seats yet attached.
- Exact environment projection of the carrier JSON.
- Licence records matched to the pinned licence repository.
- The carried records matched to the image-served records.
- Command-model records matched to the pinned Needle consumer.
- Coverage of every advertised model.
- Delivery statements checked against provisioner, offline installer, pinned voice installer, and pinned Bonsai paths, including the suite's deliberately damaged delivery paths.
- A separate artifact-binding check returned no gaps against the exact content catalog.
- The updated PDF pin test passed through the production packaged-catalog trust root.

An initial attempted Whistle receipt test could not run because `ACCEPTANCE.json` intentionally did not yet exist. Initial delivery-test attempts lacked one required local repository mapping; the delivery test passed after supplying all pinned checkouts. These are recorded limitations of those attempts, not claimed passing runs. Receipt/seat binding, complete release guard acceptance, and the full planted-defect suite must run after both seat records and the final host pin are assembled.

## Follow-up source findings

The original plain-close implementation exposed a real broker cleanup defect. In a private session, a parent forked a stopped descendant that ignored hangup. Legacy kill returned success; after 2.5 seconds the descendant remained stopped with its parent gone, while the broker itself had disappeared. The fix makes a broker with descendant tracking retain its ownership boundary and run the existing drain cleanup until all descendants are reaped. It preserves the legacy acknowledgement as request acceptance and requires no rollout-log helper.

The same independent reproduction against the fixed broker returned success with the descendant gone after 2.5 seconds. The new legacy-kill regression also passed its detached, double-forked, and stopped cases. This source change does not retrofit brokers already running older binaries.

The Go helper now allows an installed newer Debian package version to return to the exact release pin. Its eight focused tests passed, including the newer-package case. The installer still preserves unrelated command links, authenticates package acquisition, checks package contents, and selects the managed compiler for builds.

Other tests independently run during review:

- Pane-close UI: 8 passed.
- Coding handoff: 10 passed.
- OS closure selection: 85 passed.
- PDF Conversion: 241 passed, 6 skipped.

The PDF merge preserves batch input confinement while selecting the reviewed OCR implementation. No additional source blocker was found in this review.

## Remaining acceptance work

Fresh BIOS/UEFI installation, upgrades from the required prior closures, the no-rebuild Go migration, actual package installation, optional OCR/model execution, and Avatar/LLM Chat runtime checks were not performed by this seat. The PDF suite's six skips are not runtime passes. No final RC8 image or final published release is accepted by this report. The builder must assemble the final closure, attach both independent seats, run the complete carrier and release gates, and qualify the exact artifacts before publication.
