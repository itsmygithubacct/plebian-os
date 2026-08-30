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
uv run --locked --offline python run-checks.py
uv run --locked --offline python mutation-check.py
```

Without `F107B_CANDIDATE_ROOT` the runner does not pretend: **62/154** checks
skip with a reason naming the variable, it prints `PARTIAL ... NOT a full pass`
and exits **3**. If the candidate is present but its bytes have moved, the
runner refuses to run the suite at all and exits **2**.

Recorded results:

* **154/154** tests passed, **0/154** failed, **0/154** errored, **0/154** skipped.
* **15/15** deliberate mutations caught, **0/15** escaped; the restored tree is
  green again at 154/154.
* The same **154/154** reproduces under **2/2** `uv` builds — the one on PATH
  (0.12.3) and the release-pinned 0.12.5, digest
  `b65f23a420c4acc96427efb30e5ed9bc0f7e25d2d712000f6ede77c1a0de5f46` — and
  under **2/2** interpreters, CPython 3.13.5 and the 3.12.8 this packet's own
  lock resolves.
* Without the candidate: **92/154** passed, **0/154** failed, **62/154**
  skipped, exit **3**. Recorded so the partial run's shape is known in advance.

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
