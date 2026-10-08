# RC6 Whistle independent review — seat 2

I did not author this integration. I independently reviewed the optional Whistle implementation, release model contract and compliance carrier for the exact source tuple below.

Carrier CARRIER.json SHA-256: e8f90b9320e768f1151498c8b2e1552e6c2866c2e9f0bbea9be021eaa2036e9d

Reviewed source commits:
- Plebian-OS: 9eb3e0dd5e7bbe347f730b90abfa85413bc07210
- kilix: 85eb775c1ea92f2575cf8255f63d1ea767308c10
- kitty: e48a502b92cb461b4cfc838e889a64b542fa1cfe
- kilix-voice: cba6048cc7d8b6f33a1af5cc3cf84e5c1c34e802
- kilix-content: b0508c0f98e84d84c85f350ebbd6b4192147dd80
- kilix-license: b3d5f52c762d967186bd4d7b63430b057b07aa28

The source pins agree across the host, engine, Voice, Content and vendored licence authority. All five carried model artifact records match pinned Content; licence records and licence text digests match pinned licence authority. The carrier regenerates byte-identically. All 40 archived RC5 carrier files, including its seats and receipt, are preserved byte-for-byte from the preceding carrier.

I checked first-use delivery against the actual install routes: Whistle installation delegates weights to the existing model catalog agreement flow, then installs a separately pinned native library. Installation does not select a new default. The installer verifies the wheel, library and licence hashes, reads only the exact library archive member, stages an immutable generation and atomically changes the selection. Tests cover corruption, foreign paths, failed install preservation, offline reuse and platform refusal. The runtime loads explicit local files in a private child process; the reviewed implementation uses held consent-bound weights, bounded PCM/JSON, deadlines and child cleanup. A real pinned-library child smoke returned an empty transcript for silence and exited successfully on EOF. Frozen upstream artifact bytes and native library hashes were independently verified.

I found and reported two release acceptance defects in the initial OS draft: the guest validator rejected the actual five-model catalog, and its weight census omitted both Whistle stores. Commit 9eb3e0dd5e7bbe347f730b90abfa85413bc07210 fixes both. I reproduced acceptance of actual pinned Voice JSON and refusal of planted Whistle weights and dangling symlinks in both stores. The corrected tests also check Whistle catalog corruption and the explicit owner integration authorization with upstream licence evidence, without inventing end-user agreement. All carrier bytes remained unchanged. Independent isolated checks passed: 45 corrected OS contract/carrier tests, 138 Voice integration/consent/settings tests and 4 native-installer tests. A planted Whistle artifact digest change is detected; the draft release guard refuses its intentionally absent acceptance receipt.

Known issues and scope: Whistle is an optional English CPU engine supported by this integration on Linux x86-64 glibc. Turns beyond 30 seconds use native streaming and can exceed the production dictation deadline. The supplied frozen accuracy report favors Whisper small.en and records a Whistle false transcript on a non-speech control; I did not rerun the full accuracy benchmark. Whisper remains the selected/recommended default. Existing unrelated host baseline failures are not represented as passing here. No final release image, live microphone behavior, upgrade qualification or end-user licence acceptance is claimed.

This seat approves the reviewed optional source integration and unchanged carrier for binding into a final acceptance receipt. The receipt-dependent acceptance and planted-defect suite, and independent review of the final receipt-binding delta, remain required. No such final acceptance is asserted by this draft review.

VERDICT: ship with known issues
