# Owner ruling — vibevoice-asr-bitnet condition C2 amended (2026-09-29)

Amends condition **C2** of `OWNER-RULING-J1-J2-2026-09-25.md` for the Plebian-OS
0.2.2 model compliance carrier. J1, J2, C1 and C3 are unchanged.

| Item | Ruling |
| --- | --- |
| **C2 (was)** | Advertised as installable but not runnable in 0.2.2. |
| **C2 (now)** | Advertised as installable **and runnable** in 0.2.2: kilix-voice runs it as a dictation engine through the pinned VibeASR.cpp runtime (microsoft/VibeASR.cpp, MIT) that Kilix builds locally. |
| **Unchanged** | **C1**: both licences (MIT, Microsoft; Apache-2.0, Alibaba Cloud, for the Qwen2.5-1.5B decoder lineage), both licensors and both texts are listed. **C3**: the only advertised install route is the receipt-gated one (kilix-voice `require_covering_receipt`). No weights are shipped in the image or fetched by provisioning. J1: the research-only text remains an advisory. |
| **Owner's words** | Asked to make kilix-voice work: "fix vibevoice-asr-bitnet as well". Asked how the working engine should ship, given that C2 says not runnable and the carrier's delivery statements are checked against the image, the owner chose, verbatim: "Runnable in 0.2.2 (Recommended)". |
| **Consequence** | The carrier's delivery statements for vibevoice-asr-bitnet no longer say "installable in this release but not runnable". Because a determination changed, the carrier is regraded by two new independent seats, which also compare every vendored determination with its original research record. |
| Determined by | The owner (itsmygithubacct), in session on 2026-09-29. Recorded by the builder, who did not make the determination. |
