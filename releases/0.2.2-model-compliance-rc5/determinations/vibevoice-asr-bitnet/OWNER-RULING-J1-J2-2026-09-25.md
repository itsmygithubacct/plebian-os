# Owner rulings J1 and J2 — vibevoice-asr-bitnet (2026-09-25)

Supplements `OWNER-DETERMINATION-vibevoice-asr-bitnet.md` (OD-AB, 2026-09-15)
for the Plebian-OS 0.2.2 model compliance carrier (OD-BA, OQ-C2).

| Item | Ruling |
| --- | --- |
| **J1** | The VibeVoice family's "This model is intended for research and development purposes only" text is an **advisory**, not a binding condition (consistent with OD-AQ). Owner, verbatim: "J1 i agree, advisory." |
| **J2** | The two gaps OD-AB did not name were checked and found clear: **G4** training-data terms (Fisher/LDC, MLC-SLM, GPT-5 and GPT-Audio outputs, Whisper, Muse) bind the data's recipient or the output's generator, not Plebian or the user who downloads the model; **G5** the Microsoft Foundry catalogue, the model card's aka.ms links and Hugging Face's Terms of Service impose nothing beyond the model's own licences. The model repository at revision 66e78021 is not gated and carries no extra terms. Residual unknowns (undisclosed pre-training corpus; non-public LDC member, MLC-SLM 2025 and Microsoft–OpenAI agreements) are **accepted on record**. No new binding condition. Owner, verbatim: "i accept." |
| **Result** | Carry vibevoice-asr-bitnet in the 0.2.2 compliance carrier under three conditions: **C1** both licences (MIT, Microsoft; Apache-2.0, Alibaba Cloud, for the Qwen2.5-1.5B decoder lineage), both licensors and both texts are listed; **C2** it is advertised as installable but not runnable in 0.2.2; **C3** the only advertised install route is the receipt-gated one (kilix-voice `require_covering_receipt`). |
| Evidence | The J1/J2 research record, with sources and retrieval digests, is `0.2.2-branch-triage-2026-09-25/DRAFT-OWNER-DETERMINATION-vibevoice-asr-bitnet.md` in this research tree. |
| Determined by | The owner (itsmygithubacct), in session on 2026-09-25. Recorded by the builder, who did not make the determination. |
