# F107-B — first-login setup wizard and model-aware plan (fixture-backed, R1)

**Status: BUILT — AWAITING INDEPENDENT ACCEPTANCE.** Published on a `work/*`
ref for review. Nothing here is merged, released or accepted.

This is pre-gate construction. It is **not** release evidence and not hardware,
backend, model or performance qualification.

## What this tree is, and is not

It lives at `tools/setup/` beside `tools/closure/`, the same shape F120 uses for
a stream's implementation on a `work/*` ref. Two deliberate consequences:

* The Python package is named **`f107b_setup`**, not `plebian_os_setup`. F107-B
  is entry-blocked and the master records that the setup surface exists in
  **0/4** product roots. Naming this tree for the product would create, on a
  branch, the very surface that measurement says does not exist. It is named
  for the stream instead, and the measurement stays true: **no
  `plebian-os-setup` package and no installed `plebian.setup/v1` surface is
  created by this ref.**
* Nothing outside `tools/setup/` is touched. The diff against `main` is
  additive and confined to this directory.

## What is blocked, and who owns it

F107-B **cannot start** as a product stream. Both entry gates are open, and
both were re-measured rather than taken from the brief:

| Gate | Owner | Exact condition | Observed |
| --- | --- | --- | --- |
| **F100-A3** | Track A / F100 owner | F100 freezes the **F100-C0** capacity-reserve contract and publishes its exact identity, path, version and digest | F100 is at U1 R16 serial integration with **0 of 17** R16 rows admitted and U5 not entered; **6 of 6** F106 response fixtures report capacity status `missing` |
| **F106-P1** | Track D / F106 owner; F107-B is a named signatory | the P1 joint freeze of the `plebian-hardware` / `plebian-model-sizer` schemas and invocation contract, signed identical-byte by every named signatory | the current Track D input is the **R2 handoff**, which states in its own text that it is *not* the P1 joint freeze |

A third gate constrains only qualification, not construction:

| Gate | Owner | Condition |
| --- | --- | --- |
| **PHASE0-0.3** | release owner | real `plebian-hardware` / `plebian-model-sizer` binaries on real hardware |

`src/f107b_setup/gates.py` is the single place these are recorded. A capability
that is not classified against them is **refused**, not allowed.

## What was built anyway

The brief directs preparation that does not need those gates: build and test
against F106's redacted fixtures rather than Track D's implementation. That is
what this packet is.

| Module | What it is |
| --- | --- |
| `gates.py` | the gate ledger; every gated capability resolves through it |
| `f106_client.py` | the consumer half of the F106 subprocess contract — fixed argv, no shell, reduced environment, bounded streams, exit-status map |
| `admission.py` | **independent** consumer-side re-derivation of the fail-closed invariants; it does not call Track D's validator |
| `state.py` | `plebian.setup/v1` — checkpoints, skip, resume, stale refusal, atomic 0600 persistence |
| `catalog.py` | the generic `plebian.setup.optional-component/v1` offer and its two-act consent boundary |
| `licenses.py` | decision-scoped licence presentation; there is no receipt constructor |
| `plan.py` | hardware report, fit view and plan review; unknown is never rendered as zero |
| `sudoers.py` | the one-account passwordless-`sudo` drop-in |
| `syscenter.py` | System Center entries **generated from catalog data**, never committed as code |
| `TEST-INVENTORY.tsv` | the independent denominator for discovery — the F107B-01 fix |
| `browsers.py` | the default-browser question, Debian main only |
| `wizard.py` | the eight-checkpoint driver, headless and deterministic |

`TRANSCRIPT.txt` is a complete run of all eight checkpoints against the
candidate replay binaries, including every gate refusal with its owner.

## What it was built against

Track D's **reviewable R2 handoff**, not a freeze:

```
CANDIDATE-SHA256SUMS  2341c763c4ee7958387335f01a5274155311239e3c82572b1855521dc85d37f4
```

Verified **46/46** files at run time by `run-checks.py`, which refuses to run
the suite at all if the candidate does not verify. The suite references the
candidate in place rather than copying it, so a byte change there breaks these
tests loudly instead of leaving them green against a stale copy.

## Running it

The packet is self-contained apart from Track D's candidate, which is
research-side material that lives in no repository and is therefore **supplied,
not assumed**:

```sh
cd tools/setup
export F107B_CANDIDATE_ROOT=/path/to/track-d-p1-candidate
uv run --locked --offline python run-checks.py      # exit 0 only on a full pass
uv run --locked --offline python mutation-check.py  # do the tests catch a bug?
uv run --locked --offline python control-check.py   # do the controls catch a gutted suite?
```

`run-checks.py` exit statuses are distinct on purpose: **0** full pass, **1**
test failure, **2** Track D candidate mismatch, **3** partial (something
skipped), **4** the packet's own controls failed.

Without `F107B_CANDIDATE_ROOT` the runner does not pretend: the checks that need
it skip with a reason naming the variable, it prints `PARTIAL ... NOT a full pass`
and exits **3**. If the candidate is present but its bytes have moved, the
runner refuses to run the suite at all and exits **2**.

Recorded results:

* **194/194** tests passed, **0/194** failed, **0/194** errored, **0/194**
  skipped — against the **194** the committed inventory expects, not against
  itself.
* **18/18** deliberate source mutations caught, **0/18** escaped; the restored
  tree is green again at 194/194.
* **11/11** control breaches caught, **0/11** escaped (`control-check.py`).
* The same **194/194** reproduces under **2/2** `uv` builds — the one on PATH
  (0.12.3) and the release-pinned 0.12.5, digest
  `b65f23a420c4acc96427efb30e5ed9bc0f7e25d2d712000f6ede77c1a0de5f46` — and
  under **2/2** interpreters, CPython 3.13.5 and the 3.12.8 this packet's own
  lock resolves.
* Without the candidate: **132/194** passed, **0/194** failed, **62/194**
  skipped, exit **3**. The control checks still run and still pass at
  **25/25** guarded files and **12/12** modules, so a reviewer who does not
  have Track D's bytes still gets the full suite-integrity guarantee.

## Two campaigns, because there are two things to prove

`mutation-check.py` proves the **tests** catch a broken behaviour.
`control-check.py` proves the **runner** catches a broken suite. They are
separate because they answer separate questions, and the second exists because
of a finding against this packet.

**Finding F107B-01, and what it cost.** The runner used to print `tests
discovered: N/N` — a number compared to itself. Deleting a test module made `N`
smaller and the run stayed green: the loudest possible failure produced a clean
pass. The fix is two always-on controls, neither waivable:

* `SHA256SUMS` is verified for every control file — tests, fixtures, schemas,
  the inventory, the runner — before anything runs;
* `TEST-INVENTORY.tsv` gives discovery an **independent denominator**, so a
  missing module, an unexpected module or a changed count is a hard failure.

`src/f107b_setup/` is excluded from the *content* check alone, because the
mutation campaign rewrites it on purpose and a waivable control is the defect
being fixed. The division of labour is deliberate: the manifest and inventory
guard **the controls**, the tests guard **the source**, `mutation-check.py`
proves the tests do, and `control-check.py` proves the controls do.

Four of the eleven control cases **regenerate `SHA256SUMS` after tampering**, so
the content check passes and only the inventory can catch them. That is the
attack worth testing — someone who deletes a test and tidies up after
themselves — and it is the one the old runner lost to. Each case requires the
**exact** exit status naming the control that should fire (`4` for a control
failure, distinct from `1` for a test failure); "nonzero" would let an
unrelated red run masquerade as proof.

The eleventh case asserts the inverse: a source mutation must surface as a
**test** failure, not a control one. Without it, the `src/` exclusion could
silently stop holding and every mutation would score as "caught" with no test
having noticed anything.

This packet is not self-authenticating and does not claim to be. Someone who
rewrites a test *and* regenerates `SHA256SUMS` defeats the content check; what
they cannot do is change the published commit, which covers every byte
including the manifest. The git SHA is the anchor.

The mutation campaign is not decoration. Its first run caught **13/15** and let
two escape — a group-`NOPASSWD` refusal that was passing only because the
account-name pattern happened to reject the same strings, and a
plan-confirmation branch that no test ever reached because the document it used
failed admission first. Both tests were repaired; the second run is 15/15.

## What this packet deliberately does not do

* It writes **no** product file. The setup surface exists in **0 of 4**
  searched product roots and landing it needs both entry gates.
* It signs **nothing**. F107-B is a named F106 P1 signatory and there is no P1
  manifest to sign.
* It claims **no** qualification. Every consumed fixture sets
  `capture.qualification_eligible` false, and the admission rules refuse any
  document that claims otherwise.
* It writes **no** licence receipt, and exposes no function that could.
