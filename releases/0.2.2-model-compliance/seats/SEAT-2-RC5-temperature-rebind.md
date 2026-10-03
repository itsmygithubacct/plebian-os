# Independent seat 2 — RC5 Content temperature-delivery rebinding

Carrier rebinding verdict: **ACCEPT**, limited to the exact provisional carrier
and delivery change identified below. This is a fresh independent review of
these inputs. I did not author the change or consult the other reviewer for
this rebinding. Historical RC5 seats remain historical evidence; this record
does not rewrite their reviewed snapshots.

Reviewed on 2026-10-03. The OS source base is
`895328ad82ea4636d6afd8e6f67cdc37307cfe9b`; its release manifests are undergoing
the new pin/receipt binding. This review accepts the provisional carrier, not
an unfinished manifest transaction or a final release artifact.

## Exact reviewed inputs

| Input | Value |
| --- | --- |
| Provisional `CARRIER.json` SHA-256 | `d81951166a4983757499cc21c09f44396e1fc13c9f97bba6816e6328b45c140d` |
| Provisional `BINDINGS.sha256` SHA-256 | `65c0680587fa4980502334124e4fef3c11fb6dd23ec028d9795ba0cb570c3028` |
| New Content | `b7833f3f2986b1c5423898a2130bf345f04f568b` |
| Previous Content | `247d3caf1a05370b848ba0c558c6fb3bef04066f` |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` |
| Host and its Content gitlink | `d7c3a69d74c08b1bd49df5c849c480e311c41088`, Content `b7833f3f2986b1c5423898a2130bf345f04f568b` |
| Host and Content TUI-utils selection | `15c31b69e648789737c1d7f3574db200fe76848d` |
| Temperature engine | `79f427260f7499ffbe39916945428f7241f2cf37` |
| Kilix95 settings | `e65c1f8413f66749765203b2ba41f8474c28706e` |
| Content catalog SHA-256 | `d1a80a9c027bc406fe23d447e0e56a311d276e597b2f80d256ee417b51ebf778` |
| Unchanged asset/v3 schema SHA-256 | `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870` |

Provisional carrier evidence run identifier:
`0.2.2-rc5-main-merge/provisional-carrier`.

## Independent integrity and delivery findings

Comparing the complete catalog with the previous selected Git object yields
exactly one semantic difference: `/packages/0/source/ref` advances from
`d910110abf485c0e3e823989e320d19a63e1a901` to the reviewed TUI-utils commit.
The complete `assets` population is identical. The actual catalog digest
matches the updated production pin in `receipt.py`; the schema pin is
unchanged. The Content commit changes only that catalog line, its digest pin,
and the two package-selection test expectations. All 139 vendored Licence
members retain the exact modes and blob hashes of the selected Licence source.

The carrier generator, run with the exact selected Content and Licence Git
inputs and all six original determination/ruling files, passes `--check`
against the provisional carrier. Independent hashing verifies all 34 unique
binding entries, all 36 unique checksum entries, complete checksum population,
regular file types, and the binding digest recorded in `CARRIER.json`.
All 33 model, licence, notice, delivery, licence-text and determination files
are byte-identical to the preserved original carrier. The carrier JSON changes
only `interface_content_ref` and `bindings_sha256`; its environment changes
only `interface_content_ref`. Model order, runnable decisions, providers,
upstream identities, member/manifest digests, legal decisions and download
identities remain unchanged.

The host's exact Git tree selects the same Content commit and TUI-utils commit.
I independently reviewed the temperature setting's persistence and rendering:
`KILIX_TEMPERATURE_UNIT` defaults to Fahrenheit; CLI/TUI and desktop settings
persist Fahrenheit/Celsius in the shared file. Engine chrome and temperature
cards use that preference. Dashboard unit switches and its `u` key affect only
the invocation. Sensor values, alert policy, threshold arguments, JSON and CSV
remain Celsius. Shared-file changes invalidate engine chrome through its
existing reload timer.

## Executed checks and limits

I executed `tools/generate_upstream_records.py --check` for the selected
Content source; it passes. The retained Content `make check` log separately
records 314 tests passing and the generator check. I executed the carrier
generator `--check`, independent file/catalog comparisons and checksum checks,
and the real release guard against this provisional carrier with its exact
carrier digest and a zero acceptance-receipt pin. It refuses with
`ACCEPTANCE.json is missing or not a regular file` and the required release-mode
refusal line. No fictional acceptance or seat was substituted for this control.

Independent temperature checks pass: SDK/TUI 45 tests, engine tab bar 18 tests,
chrome widget 3 tests, Kilix95 settings, and the TUI-utils temperature suite
35 tests including the repository integration test. The latter uses the actual
built soft-raster library. The actual FakeScreen TUI control changes Celsius
to Fahrenheit and saves it. Additional disposable-file controls verify
SDK/dashboard agreement for defaults, existing older files, both units,
duplicate assignments and invalid values. Diff checks pass.

No model or licence consent is inferred or created by this review. No live
receipt, model installation, inference, service or VM was changed. This record
preserves the existing determinations and does not grant new model rights.
The preexisting OS README change remains excluded and untouched.

The provisional carrier contains no seats or `ACCEPTANCE.json`. The final
carrier must bind both actual fresh reviews, update the carrier and receipt
pins in both manifests, and pass the final carrier/closure checks. F101/F104,
the strict failed EnCodec capacity gate, hosted/installed-runtime qualification,
sustained and remote integration, and final ISO/upgrade acceptance remain open.
This is acceptance of the Content rebinding and temperature delivery only.

The process marker below applies to the accepted Content rebinding and
temperature-delivery source carrier with the known issues recorded here. It
does not authorize a final release or close any qualification gate.

VERDICT: ship with known issues

## Final source-selection follow-up

Before this record was bound into a new acceptance receipt, I independently
reviewed the follow-up selections. The final reviewed host is
`65edc6422e50797f248cb0bc3926eed0b87af31c`, selecting engine
`07b2932f1e3f04b3505e585f6ee46c74299d9e1f`. Kilix95
`873f48e241814d7530ff168c6734a2d53fe96714` pairs its CI with that host;
its application and test code is unchanged from the settings selection above.
These supersede the initial host/engine/Kilix95 selections in the input table.
Content, Licence, TUI-utils and the provisional carrier digests are unchanged.

The engine follow-up orders exactly two import statements. With the actual
CI Ruff version 0.16.10, both modified widget files pass. A full read-only Ruff
comparison against an independently extracted exact pre-temperature engine
`84e9f1de2b71d18fcbb0bf080ca6ea40910ac9fd` finds 36 baseline diagnostics
and 35 in the final engine, with no introduced diagnostics. The difference is
one old unused `chrome_value` import now used by the temperature formatter.
The final widget suite again passes all three tests.

The host also updates Qwen preparation's exact `CONTENT_REF` to the same
`b7833f3f2986b1c5423898a2130bf345f04f568b` selected by its Content gitlink.
Its added regression checks the actual checkout, instead of deriving a mock
ref from that constant. I independently ran the nine provider-route tests
with the selected provider source: all pass. Provider and Licence pins,
receipt checks and model identities are unchanged.

Hosted engine CI remains red for the retained run of the earlier engine:
missing Linux `libdrm-dev`, existing macOS Linux-DMA-BUF portability errors,
and baseline lint diagnostics. The relevant build/source/workflow files are
byte-identical to the exact pre-temperature engine. The selected Media SDK
likewise retains an actual failed zero-resident-page-growth check; its source
was not changed by this integration. These are not qualified or silently
waived by the temperature fix. No final hosted-CI success is asserted here.

Follow-up verdict: **ACCEPT** the reviewed source-selection corrections within
the same Content-rebinding and temperature-delivery scope. Final receipt and
manifest checks, and the release gates listed above, remain required.
