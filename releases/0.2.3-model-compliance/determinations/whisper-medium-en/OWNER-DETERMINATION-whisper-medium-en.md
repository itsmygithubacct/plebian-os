# Owner licence determination — whisper-medium-en

| Field | Entry |
| --- | --- |
| Model | Systran/faster-whisper-medium.en at revision a29b04bd15381511a9af671baec01072039215e3: the CTranslate2 conversion of OpenAI's Whisper medium.en weights (model.bin, config.json, tokenizer.json, vocabulary.txt) |
| **Licence determined** | **MIT (licensor OpenAI, for the Whisper weights; the Systran conversion is also published under MIT)** |
| Licensors | OpenAI (model weights); SYSTRAN (CTranslate2 conversion) |
| Conditions and advisories | MIT notice condition; it attaches to redistribution, which does not occur (OD-S). The Whisper model card's intended-use caution is shown as an advisory with the same text as whisper-small-en. Carrying it is a builder reading of the small.en precedent: the owner's choice named the licence and the licensors |
| First-use screen | The licence, both licensors, the advisory, and the upstream source with its pinned revision |
| Basis | The Hugging Face model card for Systran/faster-whisper-medium.en at the pinned revision, line 7 `license: mit` (sources/hf/RETRIEVAL.tsv, retrieved 2026-11-07); its file tree at that revision (same file); OpenAI's Whisper repository and model card (MIT); the whisper-small-en determination of 2026-09-29 (MIT, OpenAI and SYSTRAN, affirmative, card advisory) |
| Distribution | The user downloads the model on first use from the source. Never shipped in the image (OD-S) |
| Runtime | Offered from Plebian-OS 0.2.3 RC5 as a second Whisper dictation model: kilix-voice runs it through the pinned kilix-whisper-stt provider (faster-whisper, CTranslate2) |
| Determined by | The owner (itsmygithubacct), in session on 2026-11-07 at 22:38:59Z. Asked how to handle the medium asset's licence binding, the owner chose, verbatim: "New medium record (Recommended)". The option's text, shown to the owner: "Add a kilix-license determination for Systran/faster-whisper-medium.en @ a29b04bd (MIT; OpenAI, SYSTRAN) as your owner determination and point the asset at it." The request, verbatim, in Grok pane 31 on 2026-11-06: "set up whisper  medium on this machine and then add it to the bench" (13:36Z), "faster whisper medium english" (13:37Z), "and add whisper medium model as a model option in plebian-os 0.2.3 rc5 and onwards" (13:50Z) |
| Attestation | Recorded verbatim by the builder, who did not make the determination |
