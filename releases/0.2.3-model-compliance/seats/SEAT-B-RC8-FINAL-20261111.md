# RC8 model-compliance carrier — independent seat B

Date: 2026-11-11

VERDICT: ship with known issues

This verdict accepts the specific model-compliance carrier below. It is not acceptance of an installation image or authorization to skip release integration, upgrade, or runtime gates.

I did not author the carrier, its generator, the catalog pin update, or the implementation changes reviewed here. I reviewed them in a separate reviewer session from the builder and did not consult another seat's report.

## Exact reviewed inputs

- Carrier SHA-256: `62d0c8007feff7718dc8ccc1180f2256ca7dfaa53e52755e2a9297115e314630`.
- Content interface commit: `db463a7b32acac83d28b9ab8a1dce183e14931b2`.
- Licence interface commit: `596ada2ab68b9ec441674ff4da2d431559d47378`.
- Voice commit: `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`.
- Default-model archive SHA-256: `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.
- Default-model manifest file SHA-256: `90ee0d6448ed95a88a51b359e40567ba805d0b57ef43a7be8bf3fd5c3495a0f0`.
- Selected PDF Conversion commit: `873f3298cfe9bcbf295061cd35d5054a46f4b21a`.

The content change advances only the PDF application source revision, its catalog trust digest, and the associated pin fixtures. Model asset records are unchanged. Relative to the previous carrier, the carrier JSON changes only its content-interface reference and the digest of its bound-file inventory.

## Checks performed

The generator's `--check`, using the exact content and licence repositories and the carried determination files with no seat inputs, exited zero. It reproduced the pre-seat carrier byte for byte.

The carrier tests for byte-identical regeneration, environment projection, licence-record identity, advertised-model coverage, and delivery statements passed. The delivery test was rerun successfully with the required voice and Bonsai source repositories supplied after initial missing-repository failures. These were evidence-discovery failures, not ignored test failures.

I separately checked the artifact records against the selected content catalog with the suite's artifact comparator, checked every carried owner determination with its determination comparator, and independently recomputed every digest in `BINDINGS.sha256`. All matched. The owner determinations remain existing authority; this review invents no new owner consent or end-user licence agreement.

The PDF merge was reviewed against the previously selected application revision. It retains the OCR implementation and adds main's eager batch-source confinement checks and notice/documentation updates. Its tests passed: 241 passed, 6 skipped; lint passed.

Separate implementation follow-up: the pinned Go reconciliation defect reported by this seat was corrected in Pleb `8efc38b6799624cf8a979be1a49bb5f710f9e5a8`; all eight Debian-Go tests passed. The broker successor diff retains its subreaper during legacy termination, and its ten drain tests passed using the built broker, including detached, double-forked, and stopped descendants. These checks do not extend the carrier's cryptographic scope to those implementations.

## Known issues and remaining gates

The final host pins, acceptance receipt, and release documentation were still being assembled when these frozen carrier bytes were reviewed. The final manifest must select a Kilix commit whose content gitlink is the exact content-interface commit above, incorporate both independent seats, and pass the complete carrier suite and release guard. No receipt or final-manifest acceptance is claimed here.

Fresh-install, previous-release upgrade, actual Debian package installation, optional-model OCR, interactive pane close, and the final image's graphical/runtime checks remain separate release gates. This seat did not run them. The default-model archive hash is accepted here as the unchanged recorded carrier input; this review did not download and rehash the archive itself.
