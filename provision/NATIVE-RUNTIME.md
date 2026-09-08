# Native package transaction contract

Implementation work in progress. The five fixed helper files now have media
copy, updater staging/deployment, root snapshot/restore and checkout-bootstrap
wiring. The draft also transports the five exact native fields through release
selection, image metadata, firstboot, re-provision, updater and final provenance,
and invokes the package operation inside both enclosing OS transactions.
Private tests do not prove an installed OS deployment. Independent review of
the new outer integration and final media/upgrade qualification remain open.
No final artifact URL, checksum or source selection is supplied by these files.

## Exact release selection

`PLEBIAN_OS_NATIVE_DEB_URL`, `PLEBIAN_OS_NATIVE_DEB_SHA256`,
`PLEBIAN_OS_NATIVE_DEB_BYTES`, `PLEBIAN_OS_NATIVE_SOURCE_REF` and
`PLEBIAN_OS_NATIVE_CONTENT_REF` travel as one release-controlled selection.
All five are required for strict0.2.2. Older releases may omit the entire set;
partial selections fail even in development mode. URLs are bounded HTTPS,
with any explicit port a canonical decimal integer in1..65535 (no leading
zeros). Colons in a path or query are not treated as authority ports. Invalid
ports refuse before selection changes configuration or recovery records.
Hashes/source commits are complete lowercase identities and archives are at
most8MiB. Named manifests cannot fill omitted fields from ambient variables.
The held F120 component-root policy is unchanged. Final release pins remain
outside this implementation draft.

The unprivileged updater downloads into its private enclosing transaction;
the root provisioner uses its root-private transaction. Both use fixed curl,
timeout and prlimit tools, disable curlrc, restrict redirects to HTTPS, allow
one120-second attempt plus timeout cleanup and set an exact kernel file-size
ceiling. They compare whole length/hash before calling the root helper, which
independently validates held archive bytes. There is no model download here.

`native_package.py` inspects inert bytes using an externally selected archive
SHA-256, byte count and complete native/Content source commits. The embedded
record is only a consistency check. Inspection verifies the fixed package,
maintainer scripts, paths, modes, notices, source offer and Content record; it
does not execute a script, native code or a model. It recomputes the offered
Git tree, not the commit-object-to-tree binding. Selection of the reviewed
whole archive supplies that independent authority.

`native_runtime.py` is intended for the fixed deployed root-owned OS helper,
invoked with isolated system Python and its fixed sibling modules. There is no
CLI/environment alternate root, downloader, source builder, package-name
override or dependency-forcing mode. Library tests use explicit private roots
and a synthetic backend; that is not a production installation escape hatch.

## State and outer transaction

The private store is `/var/lib/plebian-os/native-runtime`, owned by root and
mode0700. Cached, digest-named archives, the selected current record, active
transaction token and per-transaction journals are root-only regular files.
Prior archives and journals are retained as inactive recovery material.
The helper does not copy or restore the shared global dpkg status database.

| Operation | Required state | Outcome |
| --- | --- | --- |
| `prepare [--transaction TOKEN]` | No active transaction; absent or verified managed package | Cache exact bytes and verified prior authority; use a fresh caller-recorded token or generate one; no package mutation |
| `apply TOKEN` | Prepared; original installed state and current record unchanged | Install just the selected cached package; record the actual post-state, including ordinary failures |
| `commit TOKEN` | Applied; selected files, dependencies and bookkeeping verified | Update the current record; retain rollback authority and the active token |
| `finish TOKEN` | Native committed **and enclosing stack already committed** | Verify current state and retire only the active token; retain archive/journal history |
| `rollback TOKEN` | Active, with exact before/post observations | Reinstall the verified prior archive, or purge only a package absent before this transaction |
| `rollback TOKEN --allow-unpublished` | Same active authority, or no active owner and this exact operation has not reached apply | Additionally permit absent or unpublished prepared/rolled-back history; never adopt another token or inactive applied/committed history |

The caller records a fresh token in `native-transaction` inside its existing
private outer snapshot BEFORE prepare. Preparation can fail before publishing
its journal or after publishing the active token without stranding ownership
in a lost stdout reply. A missing operation is inert; unpublished prepared
history still requires unchanged old state and intact cached authority.

Both callers invoke native rollback before restoring/removing the helper's
deployed OS layer. Native recovery failure keeps the helper and the enclosing
snapshots and does not claim an outer rollback. Native commit precedes the
irreversible enclosing commit marker (and updater generation commit); finish
follows it. A finish failure retains the coherent new installation and recovery
records, not permission to pretend the enclosing stack never committed. Inspect
both outer and native state before manual recovery. A refused prepare may
leave this caller's attempted token with no journal while a different token
owns an interrupted prior operation. Helper refusal diagnostics name the
validated active token; shell warnings distinguish the attempted token and
direct the operator to run the fixed helper's status command as root. Do not
use the attempted token as authority to retire another owner's state or restore
an OS helper it may still need. Conservative outer retention remains deliberate.
Unknown interrupted
`applying`/`recovering` state without a trustworthy post-observation requires
manual recovery; it is not automatically guessed. This is not crash atomicity.

An unknown prior installation, missing/corrupt prior archive, changed package
files/status/bookkeeping, competing active token, diversion, stat override or
missing exact dependency refuses before replacement. A change between apply
and rollback must not be overwritten merely because an old snapshot exists.
The state checks concern this package, not an unrelated package's global state.
Package maintainer scripts legitimately run the system linker-cache tool;
rollback rebuilds it through the verified old package/removal script, rather
than restoring a potentially stale global linker-cache backup.

## Locks and process lifetime

The helper first holds its named transaction lock, then follows Debian's
`/usr/share/doc/dpkg/spec/frontend-api.txt` protocol: POSIX frontend lock and
backend database lock during inspection, release only the backend lock for
the dpkg child, set `DPKG_FRONTEND_LOCKED`, and reacquire the backend lock after
the owned command tree finishes. Named lock identities remain checked through
the handoff. An ordinary busy lock refuses without waiting indefinitely.

The dedicated CLI enables Linux subreaping, uses a fixed clean command
environment and one original180-second operation deadline, and bounds combined
command output to1MiB. Cancellation/expiry/guard loss kills and reaps owned
commands, including escaped adopted descendants, before any successful return.
Cleanup has a separate five-second ceiling: failure to prove cleanup reports
incomplete recovery, never success. A distinct15-second post-operation observer
can retain a failed operation's actual state; it does not renew forward-install
or rollback-success authority. Rollback's post-observation must still equal
the exact original package state, and the original cancellation/deadline check
must pass before success bookkeeping. Otherwise the observed state and active
token remain as recovery-failed. Ownership also covers an actual child fork
whose Popen constructor fails before returning a handle. Persistent system-wide
resource exhaustion is not qualified.

This is a trusted-root deployment contract, not a sandbox against another root
process. Root-managed directory ancestors must remain in their named locations
throughout the operation; held-parent lock checks alone do not prove that a
replaced ancestor still resolves to the held tree. Similarly, verified cached
archive entries must remain unchanged until dpkg has consumed them. Dpkg opens
the selected pathname itself; this helper does not pass it a sealed immutable
archive descriptor. Root ownership, private modes and package-manager locks
exclude unprivileged writers and cooperating package managers, not arbitrary
concurrent trusted-owner pathname replacement. C14's conditional ancestor/cache
replacement observations remain documented limits, not fixed controls.

The successor uses explicit --triggers and requires clean package-manager audits
before/after mutation; a zero dpkg --audit exit alone is insufficient. Before
mutation the audit covers every enumerated package except this exact managed
package, which may be partially installed in a journal-bound recovery. It never
excludes libc-bin or another package. Successful verification audits the entire
database. Pre-existing unrelated pending work, or an unresolved libc-bin trigger
failure, refuses without running arbitrary --configure/--pending repair. The
genuine earlier direct-dpkg --no-triggers fixture remains unchanged evidence of
its pending-state defect. These new command-boundary tests still require actual
helper execution with the genuine packages; no installed acceptance is inferred.

## Tests and remaining integration

The focused tests separate inert selected synthetic artifacts, actual private
filesystem operations, a clearly synthetic package backend, and dedicated real
process/lock controls. Actual namespace/chroot dpkg tests must independently
exercise the genuine package/dependency population. They must never install on
the host, use chrootless maintainer scripts or fake installed dependencies.

The added outer tests run real shell/configuration and private root-snapshot
operations with an explicitly synthetic helper peer. Downloader tests replace
only curl with an inert writer while executing the real kernel file-size limit
and timeout; they do not qualify real HTTPS transport. Separate core tests cover
caller-token collision, unpublished preparation, missing cached authority,
foreign ownership and refusing inactive applied/committed history. Existing
actual helper/package evidence predates this new caller-token interface and
must not be transferred to it as full installed acceptance.

Before shipping, independently review the new API and outer rollback ordering,
test actual deployed helpers/download/OS transactions on the exact final source,
finish native package and pending-work qualification, and execute final media
and021-upgrade gates. The final runtime selection, GPU/model quality and owner
release gates remain open; neither private test success nor a local source
snapshot is release approval.
