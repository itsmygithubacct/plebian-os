# Model-consumer integration evidence

`verify-model-integration.py` checks an **unselected** proposal against a local
root. It never downloads models, imports provider code, installs a runtime,
changes a selected pin, or issues a consent receipt. Run it before staging a
multi-provider composition; retain its gaps beside the original review results.

```sh
python3 build/verify-model-integration.py --root /path/to/evidence \
  --manifest /path/to/proposal.json
```

Exit 0 means that the supplied local identities match. `--require-complete`
returns 2 when any dependency, review, license, packaging, quality or admission
gap remains. Malformed evidence or an identity mismatch returns 1. Even a
complete report is not release acceptance. It validates declared evidence, not
the authority or truth of an independently signed decision.

The JSON schema identifier is `plebian-os.model-integration/v1`. Required fields:

- `selection`: `unselected`; `release_accepted`: `false`.
- `files`: nonempty records with unique `id`, relative `path`, `bytes`, `sha256`.
  Include frozen handoffs, package/lock identities and public receipt evidence.
- `sources`: nonempty records with unique `id`, relative repository `path`,
  exact `head` and `tree`, and `gitlinks` mapping every tracked submodule path
  to its exact commit. Each source must be clean, have connected full history,
  own its Git directory and have no alternates. Every unverified child checkout
  produces a gap; listing a parent commit does not establish recursive closure.
- `profiles`: nonempty records with unique `id`, nonempty `sources` and `files`
  lists referencing those inventories, and descriptive `abi`, `cpu`, `install`,
  `relocation` and `rollback` strings. These strings document assumptions;
  they do not replace a target-machine execution or rollback test.

Each profile additionally records `review` (`state`: `pending`, `failed`, or
`complete`); `license` (`existing-binding`, `missing`, or `pending`);
`license_evidence` (file IDs); `packaging` (`verified` or `pending`); `quality`
(`qualified`, `pending`, or `no-go`); and `admission` (`admitted`, `pending`, or
`no-go`). Existing license bindings require evidence. Do not put private user
receipt contents into a shareable report; bind an appropriate public audit.

A complete review requires `review.file` to reference a hashed JSON handoff
with `complete: true`, `source_heads` exactly matching the profile's source IDs
and commits, and `original_verdict` (`pass` or `fail`). An original failure stays
`fail`; its repair additionally requires `repair_independent_review: pass`.
An adapter to a different review format should preserve and hash the original
handoff too. A mutable status file or an engineering self-check cannot stand in
for that completed independent evidence.

Paths must remain inside the evidence root. Duplicate JSON keys and IDs are
refused. Keep the evidence tree immutable during verification. This verifier
is a local audit, not an atomic installation guard: a subsequent installer must
recheck the same bytes, obtain actual first-use authorization through the
existing Content/License authority and retain its coherent rollback selection.

Run the offline regressions with:

```sh
python3 -B -m unittest discover -s tests -p test_model_integration.py -v
```
