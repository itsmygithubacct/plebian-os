# Owner licence determination — vibevoice-asr-bitnet

| Field | Entry |
| --- | --- |
| Model | microsoft/VibeVoice-ASR-BitNet at revision 66e78021 (fetched via kilix-bonsai) |
| **Licence determined** | **MIT (licensor Microsoft), with a component exception: the Qwen2.5-1.5B decoder lineage is Apache-2.0 (licensor Alibaba Cloud)** |
| Licensors | Microsoft Corporation (model); Alibaba Cloud (Qwen2.5-1.5B decoder lineage) |
| Conditions and advisories | MIT notice condition; Apache-2.0 §4 attaches to redistribution, which does not occur (OD-S). The VibeVoice family's "research and development purposes only, not recommended for commercial or real-world use without further testing" advisory is shown as an advisory |
| First-use screen | Both licensors and both licences, the component exception, and the research-use advisory quoted verbatim, with the upstream source and pinned revision |
| Basis | Weight card at the pinned revision (licence YAML, badge, sentence, API tag); base VibeVoice-ASR card, unchanged across 15 commits; MIT LICENSE of both official Microsoft code repositories; report, VibeASR.cpp and config.json showing a replaced Qwen2.5-1.5B decoder |
| **Accepted gaps, on record** | No LICENSE, NOTICE or copyright line accompanies the weights. Microsoft's two code-repository copyright lines differ. Microsoft does not address the Qwen2.5 contribution, so the exception rests on the builder evidence packet's lineage analysis. |
| Distribution | **The user downloads the model on first use from the source (owner, restated with this determination).** Never shipped (OD-S). |
| Runtime note (not a licence matter) | In 0.2.2 the engine is runtime_supported=False and the daemon refuses it; that is tracked in the fix programme, not here |
| Determined by | The owner (itsmygithubacct), in session on 2026-09-15. Verbatim: "2, but the user downloads any models on first use" |
| Attestation | Recorded verbatim by the builder, who did not make the determination |
