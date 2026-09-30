# Independent seat 2 — separate RC4 laptop carrier

Reviewed commit: `7ff93259f6eecbcffab7474c826c8347aba9a60e`.

I did not author the laptop carrier, its owner determinations, or its selected code.

I examined this exact pre-seat independently in
`/tmp/rc4-laptop-seat2.oPMmdR/os`, extracted with `git archive`. All executions
and planted defects used private temporary copies. No findings or evidence
from the other laptop seat were consulted.

## Findings

No new carrier defect was found at High, Medium, or Low severity. The source
delta preserves the speech payload and binds it to the laptop host's actual
content gitlink. The release-notes table already contains the correct content
SHA, and the full OS run found no unrelated source failure.

**Medium, existing qualification limit:** the reported hosted engine workflow
remains non-green, including the libdrm, lint and macOS limitations. This
offline review did not execute that workflow, and does not turn those prior
results into passes. The engine is still the same selected commit.

**Low, coverage limit:** three checks skip in these archives: the historical
provisioner check lacks a local `v0.2.1` tag; the released native inspector is
absent; and the desktop-session identity check has no sibling pleb checkout.
Their skip messages are preserved. They are not included as successful checks.

**Required pre-seat refusal, observed:** the actual artifact has neither
`ACCEPTANCE.json` nor seat files. Its guard exits 1 with the specific missing
acceptance error and the release-mode refusal. An acceptance receipt containing
the actual independent records and its final validation remain subsequent work.

## Source and artifact checks

The selected closure is:

| Input | Exact selected object |
| --- | --- |
| Host | `296a8f862176991d023061e4a2bd8df6e5df0625` |
| Host content gitlink | `191abbcbf11ceae03f40e732c20d394c8d53578a` |
| Desktop provider | `cea38b7f6a85a473877888f0250fb8083e6a7e33` |
| Host engine gitlink | `84e9f1de2b71d18fcbb0bf080ca6ea40910ac9fd` |
| Voice | `a12be47e289ca03fccd46840276add1833df5760` |
| Licence records | `993c8ec0df87c677521652b7c3a8ca9797ce2cba` |

I read the exact Git objects, rather than the working-tree copies. Both host
gitlinks have mode `160000` and equal the expected full SHAs. The desktop
provider's sole change from the frozen VM selection is the exact-host CI pin.
The carrier content value agrees in the notes table, release environment and
requirements. Every selected commit value checked is 40 lowercase hex characters.

Against accepted VM OS `f962317a4d49cc1e81acecfb9c9955bc5b24a800`, only four
manifest values move: host, desktop provider, carrier content and carrier digest.
Native package/source/content inputs, the model archive and speech-library
inputs, licence pin, voice pin and model-sizer pin do not move. No build or
provisioning source file changes.

I compared all 32 entire asset mappings at frozen VM content
`2f5f3d7c28fdfe088ea24573f4c7fceea1f53013` and laptop content `191abbcb`.
They are equal, including all fields and member digests. All four speech entries
in the carrier are also equal. The carrier JSON differs only in the producing
content ref and the digest derived from its bindings. Content's delta contains
the Needle application ref, its catalog trust digest and the changelog.

I compared 17 host speech/model paths as Git blobs and found each unchanged
from host `e97e52a98e2babe6220ee0f3d2f5f4e06ff01f66`. The host launcher changes
only its help line. I reviewed the added context collection and control changes:
they collect installation/connection facts and retain the existing speech
dispatch and model-install routes. No speech installer is changed. Whisper's
runtime remains `15ef23b32da497a41198d3028e34715801de6196` with locked dependency
sync; the existing receipt and verified-download checks continue to pass in
the OS delivery tests.

For every one of the six owner documents, I compared the ORIGINAL source path
from `PREPARATION.json`, this archive's vendored bytes, and the accepted VM's
vendored bytes. All three agree; the independently computed SHA-256 values also
agree with the preparation listing. I regenerated from those six ORIGINAL
documents, in sorted model/path order, using the exact content and licence
object inputs. All **37 files** match the pre-seat byte-for-byte. The carrier
digest is `0293655bcae0fa4380a4f89025c1fe50dce294a7f7781d576badaa734cb36709`,
and both manifests name it.

## Executed checks

| Execution | Result |
| --- | --- |
| Exact pre-seat full OS suite | 904 tests; 10 failure reports, 21 error reports, 3 skips |
| Private synthetic-acceptance full OS suite | 904 tests; OK, 3 skips |
| Carrier tests within that private suite | 15/15 pass, including supplied defect cases |
| Exact archive authority-profile suite | 6/6 pass |
| Independently designed guard experiments | 18/18 expected outcomes |

I inspected the exact-pre-seat tracebacks: every failure/error report is
caused by absent acceptance or seats, including mutation helpers that require
them. None is a content, delivery, notes-table, or native-input failure. The
synthetic control adds two distinct files explicitly marked private test input
and NEVER USE AS A RELEASE REVIEW; the generator produces its private receipt,
whose digest is updated only in that temporary copy. These files stay outside
the release evidence directory and are never usable as actual review records.

The independent guard experiments test the new laptop pins directly. Returning
only the host to the frozen VM selection is refused. My own two-commit local
host fixture supplies either the correct content gitlink or one differing only
in its last hex character; the latter is refused despite its matching
39-character prefix. Consistently re-pinning a carrier and manifests to unserved
content also fails. Uppercase host refs and truncated host refs fail, including
a 12-character ref that resolves to a deliberately created private branch.

The acceptance controls reject changed receipt bytes, a freshly pinned receipt
for another carrier, one remaining review with a regenerated acceptance pin,
and an equal-byte seat symlink. The binding controls reject a modified notice
after checksum regeneration and a duplicate environment key even after full
private re-pinning.

I then weakened three individual validator conditions in private function text:
the full content comparison became a 12-character comparison, the 40-character
host rule became a nonempty check, and the receipt digest comparison was removed.
Each mutant wrongly admits its corresponding planted defect. The original
validator refuses all three, demonstrating that these experiments exercise the
specific checks rather than an earlier missing-acceptance refusal.

Each suite used `env -i`, temporary HOME, PATH `/usr/bin:/bin`, and `python3 -B`.
The OS suite also used explicit content, licence, voice, host and bonsai source
overrides from `PREPARATION.json`. Authority discovery ran from the exact archive
with `-s tools/closure/tests -t tools/closure`. Logs, scripts and checksums are
preserved beside this record in `laptop-seat-2-evidence/`.

## Limits

This is an offline laptop carrier assessment. It establishes neither an image
build nor native package verification, laptop runtime acceptance, installation
success, or benchmark reliability. I did not read held-out/task data, invoke an
installed launcher, access the live store, install anything, accept a licence,
download models, run setup, reboot, publish, or change original repositories or
refs. The unchanged speech runtime was not retranscribed. The full OS suite's
source-level weight checks are not a fresh inspection of a built image.

VERDICT: ship with known issues
