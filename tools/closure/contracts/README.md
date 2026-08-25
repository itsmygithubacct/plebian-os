# F120 candidate closure contracts

These language-neutral Draft 2020-12 JSON Schemas are **frozen v1 contracts**.
The recorded review closed every finding and the locked two-pass freeze gate
passed on 2026-08-19. Incompatible changes require a new schema identity; v1
may receive only clarifications that do not alter accepted documents. These
contracts do not implement resolution, fetching, building, staging, pin
updates, or release selection.

- `schemas/kilix.f120.workspace-manifest-v1.schema.json` records an observed
  workspace, including honest dirty or unresolved state.
- `schemas/kilix.f120.release-lock-v1.schema.json` records a clean, exact,
  qualified closure and binds staged artifacts to component source/build
  inputs.
- `validate_f120.py` performs Draft 2020-12 validation and graph checks that
  JSON Schema cannot express: referential integrity, cycles, qualification
  state, feature ordering, artifact binding, and conflicting revisions of a
  native provider reachable in one runtime process.

Run the complete golden-fixture gate with an isolated uv environment:

```sh
cd f120-contracts
uv run --locked python validate_f120.py --self-test
```

Validate another document with:

```sh
cd f120-contracts
uv run --locked python validate_f120.py PATH.json
```

Workspace manifests are checked as qualification inputs by default. Pass
`--allow-development-state` only to inventory an intentionally dirty or
unresolved development workspace; it never applies to a release lock.

Every schema and fixture is canonical UTF-8 JSON with sorted keys, two-space
indentation, and one final newline. `SHA256SUMS` pins the README, validator,
schemas, and fixtures so the complete candidate package is byte-bound.
