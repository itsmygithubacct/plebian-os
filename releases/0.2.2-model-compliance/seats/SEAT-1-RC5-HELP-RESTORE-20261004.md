# Independent F100 seat 1 — RC5 Help Search restoration

VERDICT: ship

This verdict covers the restored source selections and regenerated F100 carrier for Plebian-OS 0.2.2. I did not author the source changes or the carrier generator. I reviewed independently without reading the other new seat's report. No blocking defect was found. This is source and carrier qualification; it does not claim runtime VM, ISO, or release-artifact qualification.

Reviewed selection:

- OS integration based on `7d44dea`, with the release manifest selecting the sources below.
- Kilix host `e76ea0beb4c7d3340490e6d2dc3bd1a97bd9f3ab`.
- Kilix95 `03da5ffb303c1483a733b4bd2230c13612b4871c`.
- Content `1210151be1757d8f62b402b7b3196e1564d976b3`.
- Needle `7de641763c403f8c54873ef4d044277c946d4445`.
- TUI utilities `8b461045715f176218c57b17ff16ccfd756aace1`.
- Licence interface `ca8a0f479893ab9c8cd6cadc2716c474aaad2820`; voice `a12be47e289ca03fccd46840276add1833df5760`.
- Reviewed `CARRIER.json` SHA256: `96ec0550c5adb5bcd155102cdb0fe3d82fdce65ff82a2001ebfdd2079290de79`.

The exact host gitlink serves the selected Content commit. Its TUI installer agrees with the Content package selection, and Needle's exact gitlink selects that same TUI commit. TUI retains the preceding workflow commit as an ancestor. The final Kilix95 commit preserves its Help Search merge and pins CI to the exact reviewed host. Both desktop search entry points pass questions as argv to the existing cited-document lookup.

Compared Content with the preceding RC5 selection `21c6f503ea3a9e5a094724f572a2310ea5ad55ba`: all 32 asset records and the asset/v3 schema are unchanged. Catalog changes select Needle and TUI, and the production catalog trust digest correctly changes to `e7791219f3728afa087fc4af9ae3a544266a9b9a2a4cbe27bc606c075f090205`. The unchanged schema digest is `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870`.

The provisional carrier has 37 regular files and verifies with its SHA256SUMS. Compared with the preceding accepted RC5 carrier, only CARRIER.json, CARRIER.env, BINDINGS.sha256 and SHA256SUMS change. All 33 model, licence-text and determination files remain byte-identical. The four carried models retain their source URLs, digests, affirmative licence records, licensors, runnability and first-use delivery. The VibeVoice J1/J2 ruling and C2 amendment remain bound unchanged. Licence records match the exact pinned licence source. Carrier generation from pinned objects reproduces the provisional directory byte for byte. The carrier's model artifacts match the records actually served by the host.

Independent validation passed:

- Content: 39 tests covering consumer selections, contracts, absent shipped weights, Vosk, Whisper and VibeVoice records.
- Host: 42 tests covering catalog pin delivery, consumer selections and model licence/receipt behavior.
- F100: seven existing tests redirected in memory to the provisional carrier, covering regeneration, JSON/env projection, pinned licence records, served artifacts, advertised coverage, delivery/receipt gates and refusal without a carrier. A separate pinned artifact comparison found no gaps.
- Exact TUI source archive: four Help Search tests, including installed launcher delivery.
- Exact Kilix95 checkout paired with the reviewed host: Help Search and Start-menu test scripts both passed.

Acceptance implication: this report is an input to the new acceptance receipt. The reviewed provisional carrier intentionally has no ACCEPTANCE.json or seat records. Final assembly must bind the two new independent reports, update carrier and receipt digests in both release files, regenerate the complete inventory and pass the full F100 suite, including receipt, acceptance-guard, defect-refusal and release-pin checks. The old receipt cannot qualify the newly selected Content interface. No new model or licence determination is required by these source-selection changes.
