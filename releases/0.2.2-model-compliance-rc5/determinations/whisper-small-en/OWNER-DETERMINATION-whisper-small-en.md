# Owner licence determination — whisper-small-en

| Field | Entry |
| --- | --- |
| Model | Systran/faster-whisper-small.en at revision d1d751a5f8271d482d14ca55d9e2deeebbae577f: the CTranslate2 conversion of OpenAI's Whisper small.en weights (model.bin, config.json, tokenizer.json, vocabulary.txt) |
| **Licence determined** | **MIT (licensor OpenAI, for the Whisper weights; the Systran conversion is also published under MIT)** |
| Licensors | OpenAI (model weights); SYSTRAN (CTranslate2 conversion) |
| Conditions and advisories | MIT notice condition; it attaches to redistribution, which does not occur (OD-S). The Whisper model card's cautions (it can hallucinate text that was not spoken, and accuracy varies with accent, language and recording conditions) are shown as an advisory, as for whisper-tiny-ggml |
| First-use screen | The licence, both licensors, the advisory, and the upstream source with its pinned revision |
| Basis | Hugging Face model card and API licence tag `mit` for Systran/faster-whisper-small.en at the pinned revision; OpenAI's Whisper repository and model card (MIT); the existing whisper-tiny-ggml record (MIT, OpenAI, affirmative, card advisory) |
| Distribution | The user downloads the model on first use from the source. Never shipped in the image (OD-S) |
| Runtime | Installable and runnable in 0.2.2: kilix-voice runs it for dictation through the pinned kilix-whisper-stt provider (faster-whisper, CTranslate2 int8 on CPU) |
| Determined by | The owner (itsmygithubacct), in session on 2026-09-29. Asked to accept MIT with the card cautions carried as an advisory, the owner chose, verbatim: "I accept (MIT, advisory)". Asked which runtime RC3 should ship, the owner chose, verbatim: "faster-whisper (Recommended)". The request, verbatim: "set whisper small.en in the model sizer as the default model for a system of this hardware capability and on first boot of the plebian-os or until set yes or no, have it offer to install whisper small english or whatever default model for the user and set up dictation" |
| Attestation | Recorded verbatim by the builder, who did not make the determination |
