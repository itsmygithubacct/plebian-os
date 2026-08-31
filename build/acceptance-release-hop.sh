#!/usr/bin/env bash
# acceptance-release-hop.sh — F109's two-shape, real-guest release-hop lane.
#
# Run this only inside a disposable VM whose installed closure is the accepted
# previous release.  The runner plants checkout and application-state
# sentinels, induces one selector-transaction failure, proves compensation,
# performs the successful hop with one `pleb update --to` command, and emits a
# checksummed evidence directory.  It deliberately does not create tags or a
# release manifest: those are release-owner inputs, not qualification output.
set -euo pipefail

usage() {
    cat <<'EOF'
usage: acceptance-release-hop.sh --shape image|standalone --from X.Y.Z \
       --target X.Y.Z --from-pleb-ref SHA --from-kilix-ref SHA \
       --report DIR --disposable-vm [--pleb PATH] [--pleb-dir DIR] \
       [--kilix-dir DIR] [--session-env FILE] [--closure-env FILE] \
       [--from-os-ref SHA --from-kilix95-ref SHA \
        --expected-build-info-sha256 SHA256]

The guest must start on the accepted previous release. DIR must be outside
$HOME. Image guests require all three final options. The command refuses
non-VM hosts, a dirty source checkout, or a starting closure mismatch.
EOF
}

die() {
    printf 'acceptance-release-hop: %s\n' "$*" >&2
    exit 1
}

shape=""
from=""
target=""
report=""
from_pleb_ref=""
from_kilix_ref=""
from_os_ref=""
from_kilix95_ref=""
expected_build_info_sha256=""
pleb_bin=""
pleb_dir=""
kilix_dir=""
session_env=""
closure_env=""
disposable=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --shape) [ "$#" -ge 2 ] || die "--shape needs a value"; shape="$2"; shift 2 ;;
        --from) [ "$#" -ge 2 ] || die "--from needs a value"; from="$2"; shift 2 ;;
        --target) [ "$#" -ge 2 ] || die "--target needs a value"; target="$2"; shift 2 ;;
        --from-pleb-ref) [ "$#" -ge 2 ] || die "--from-pleb-ref needs a value"; from_pleb_ref="$2"; shift 2 ;;
        --from-kilix-ref) [ "$#" -ge 2 ] || die "--from-kilix-ref needs a value"; from_kilix_ref="$2"; shift 2 ;;
        --from-os-ref) [ "$#" -ge 2 ] || die "--from-os-ref needs a value"; from_os_ref="$2"; shift 2 ;;
        --from-kilix95-ref) [ "$#" -ge 2 ] || die "--from-kilix95-ref needs a value"; from_kilix95_ref="$2"; shift 2 ;;
        --expected-build-info-sha256) [ "$#" -ge 2 ] || die "--expected-build-info-sha256 needs a value"; expected_build_info_sha256="$2"; shift 2 ;;
        --report) [ "$#" -ge 2 ] || die "--report needs a value"; report="$2"; shift 2 ;;
        --pleb) [ "$#" -ge 2 ] || die "--pleb needs a value"; pleb_bin="$2"; shift 2 ;;
        --pleb-dir) [ "$#" -ge 2 ] || die "--pleb-dir needs a value"; pleb_dir="$2"; shift 2 ;;
        --kilix-dir) [ "$#" -ge 2 ] || die "--kilix-dir needs a value"; kilix_dir="$2"; shift 2 ;;
        --session-env) [ "$#" -ge 2 ] || die "--session-env needs a value"; session_env="$2"; shift 2 ;;
        --closure-env) [ "$#" -ge 2 ] || die "--closure-env needs a value"; closure_env="$2"; shift 2 ;;
        --disposable-vm) disposable=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[ "$disposable" = 1 ] || die "refusing to run without --disposable-vm"
case "$shape" in image|standalone) ;; *) die "--shape must be image or standalone" ;; esac
[[ "$from" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "--from must be X.Y.Z"
[[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "--target must be X.Y.Z"
[ "$from" != "$target" ] || die "--from and --target must differ"
for named_ref in "$from_pleb_ref" "$from_kilix_ref"; do
    [[ "$named_ref" =~ ^[0-9a-f]{40}$ ]] || die "starting Pleb and Kilix refs must be full lowercase commit SHAs"
done
if [ "$shape" = image ]; then
    [[ "$from_os_ref" =~ ^[0-9a-f]{40}$ ]] || die "image shape requires --from-os-ref as a full lowercase commit SHA"
    [[ "$from_kilix95_ref" =~ ^[0-9a-f]{40}$ ]] || die "image shape requires --from-kilix95-ref as a full lowercase commit SHA"
    [[ "$expected_build_info_sha256" =~ ^[0-9a-f]{64}$ ]] \
        || die "image shape requires --expected-build-info-sha256"
else
    [ -z "$from_os_ref$from_kilix95_ref$expected_build_info_sha256" ] \
        || die "standalone shape does not accept image-only starting-fixture options"
fi
[ -n "$report" ] || die "--report is required"
command -v git >/dev/null 2>&1 || die "git is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required"
command -v systemd-detect-virt >/dev/null 2>&1 \
    || die "systemd-detect-virt is required to prove the guest boundary"
virt="$(systemd-detect-virt --vm 2>/dev/null || true)"
if [ -z "$virt" ] || [ "$virt" = none ]; then
    die "this host is not detected as a VM; use a disposable VM"
fi

installed_pleb="$(command -v pleb 2>/dev/null || true)"
if [ -z "$pleb_bin" ]; then pleb_bin="$installed_pleb"; fi
if [ -z "$pleb_bin" ] || [ ! -x "$pleb_bin" ]; then
    die "no executable pleb command found"
fi
pleb_bin="$(readlink -f -- "$pleb_bin")"
installed_pleb="$(readlink -f -- "$installed_pleb" 2>/dev/null || true)"
pleb_code_root="$(cd "$(dirname -- "$pleb_bin")/.." && pwd -P)"
if [ -z "$pleb_dir" ]; then
    pleb_dir="$pleb_code_root"
fi
source_home="${GPU_TERMINAL_SOURCE_HOME:-$HOME/.local/gpu_terminal/sources}"
if [ -z "$kilix_dir" ]; then
    kilix_dir="$source_home/kilix"
fi
pleb_dir="$(cd "$pleb_dir" && pwd -P)"
kilix_dir="$(cd "$kilix_dir" && pwd -P)"
[ -d "$pleb_dir/.git" ] || die "Pleb is not a git checkout: $pleb_dir"
[ -d "$kilix_dir/.git" ] || die "Kilix is not a git checkout: $kilix_dir"

if [ -z "$session_env" ]; then
    if [ "$shape" = image ]; then
        session_env="/etc/pleb/session.env"
    else
        session_env="${PLEB_CONFIG_HOME:-$HOME/.local/gpu_terminal/pleb/config}/session.env"
    fi
fi
if [ -z "$closure_env" ]; then
    closure_env="$(dirname -- "$session_env")/closure.env"
fi

mkdir -p -- "$report"
report="$(cd "$report" && pwd -P)"
home_root="$(cd "$HOME" && pwd -P)"
case "$report" in "$home_root"|"$home_root"/*)
    die "--report must be outside HOME so the full-tree manifests do not include themselves" ;;
esac
[ -z "$(find "$report" -mindepth 1 -maxdepth 1 -print -quit)" ] \
    || die "report directory must be empty: $report"
chmod 0700 "$report"

checks="$report/checks.tsv"
: >"$checks"
check_total=0
check_pass=0
record_check() {
    local name="$1" result="$2" detail="$3"
    check_total=$((check_total + 1))
    if [ "$result" = pass ]; then check_pass=$((check_pass + 1)); fi
    printf '%s\t%s\t%s\n' "$name" "$result" "$detail" >>"$checks"
}
must() {
    local name="$1" detail="$2"
    shift 2
    if "$@"; then
        record_check "$name" pass "$detail"
    else
        record_check "$name" fail "$detail"
        die "$name failed: $detail"
    fi
}

path_fingerprint() {
    local path="$1"
    if [ -L "$path" ]; then
        printf 'symlink:%s\n' "$(readlink -- "$path")"
    elif [ -f "$path" ]; then
        printf 'file:%s:%s\n' "$(stat -c '%a' -- "$path")" \
            "$(sha256sum -- "$path" | awk '{print $1}')"
    elif [ -d "$path" ]; then
        printf 'directory:%s\n' "$(stat -c '%a' -- "$path")"
    elif [ -e "$path" ]; then
        printf 'other\n'
    else
        printf 'absent\n'
    fi
}

home_manifest() {
    local output="$1"
    HOME_ROOT="$home_root" python3 - "$output" <<'PY'
import hashlib
import os
import stat
import sys
from pathlib import Path

root = Path(os.environ["HOME_ROOT"])
rows = []
for directory, names, files in os.walk(root, topdown=True, followlinks=False):
    names.sort()
    files.sort()
    for name in [*names, *files]:
        path = Path(directory) / name
        rel = path.relative_to(root).as_posix()
        st = path.lstat()
        mode = format(stat.S_IMODE(st.st_mode), "04o")
        if path.is_symlink():
            kind, value = "symlink", os.readlink(path)
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            kind, value = "file", digest.hexdigest()
        elif path.is_dir():
            kind, value = "directory", "-"
        else:
            kind, value = "other", "-"
        rows.append((rel, kind, mode, value))
Path(sys.argv[1]).write_text(
    "".join("\t".join(row) + "\n" for row in sorted(rows)),
    encoding="utf-8",
)
PY
}

git_snapshot() {
    local repo="$1" prefix="$2"
    git -C "$repo" rev-parse HEAD >"$report/$prefix.head"
    git -C "$repo" status --porcelain=v1 --untracked-files=all \
        >"$report/$prefix.status"
}

must "guest-is-disposable-vm" "$virt" test -n "$virt"
must "installed-pleb-entrypoint-is-tested" "$installed_pleb" \
    test -n "$installed_pleb" -a "$pleb_bin" = "$installed_pleb"
must "entrypoint-matches-participating-pleb-checkout" "$pleb_dir" \
    test "$pleb_code_root" = "$pleb_dir"
must "pleb-checkout-starts-clean" "$pleb_dir" test -z \
    "$(git -C "$pleb_dir" status --porcelain=v1 --untracked-files=all)"
must "kilix-checkout-starts-clean" "$kilix_dir" test -z \
    "$(git -C "$kilix_dir" status --porcelain=v1 --untracked-files=all)"
pleb_start_head="$(git -C "$pleb_dir" rev-parse --verify 'HEAD^{commit}')"
kilix_start_head="$(git -C "$kilix_dir" rev-parse --verify 'HEAD^{commit}')"
must "starting-pleb-ref-is-exact" "$pleb_start_head/$from_pleb_ref" \
    test "$pleb_start_head" = "$from_pleb_ref"
must "starting-kilix-ref-is-exact" "$kilix_start_head/$from_kilix_ref" \
    test "$kilix_start_head" = "$from_kilix_ref"
must "session-env-exists" "$session_env" test -f "$session_env"

if [ "$shape" = standalone ]; then
    must "standalone-has-no-system-session" "/etc/pleb/session.env" test ! -e /etc/pleb/session.env
    must "standalone-has-no-os-source" "$source_home/plebian-os" test ! -e "$source_home/plebian-os"
    must "standalone-has-no-os-updater" "/usr/local/bin/plebian-os-update" test ! -e /usr/local/bin/plebian-os-update
    must "standalone-has-no-os-selector" "/usr/local/bin/plebian-os-select-closure" test ! -e /usr/local/bin/plebian-os-select-closure
else
    os_dir="$source_home/plebian-os"
    kilix95_dir="$source_home/kilix-desktops/kilix-95"
    must "image-has-system-session" "/etc/pleb/session.env" test -f /etc/pleb/session.env
    must "image-has-os-updater" "/usr/local/bin/plebian-os-update" test -x /usr/local/bin/plebian-os-update
    must "image-has-os-selector" "/usr/local/bin/plebian-os-select-closure" test -x /usr/local/bin/plebian-os-select-closure
    must "image-has-installed-build-info" "/etc/plebian-os/build-info.env" \
        test -f /etc/plebian-os/build-info.env
    installed_build_info_sha256="$(sha256sum /etc/plebian-os/build-info.env | awk '{print $1}')"
    must "image-build-info-matches-published-fixture" \
        "$installed_build_info_sha256/$expected_build_info_sha256" \
        test "$installed_build_info_sha256" = "$expected_build_info_sha256"
    must "image-os-checkout-exists" "$os_dir" test -d "$os_dir/.git"
    must "image-kilix95-checkout-exists" "$kilix95_dir" test -d "$kilix95_dir/.git"
    os_start_head="$(git -C "$os_dir" rev-parse --verify 'HEAD^{commit}')"
    kilix95_start_head="$(git -C "$kilix95_dir" rev-parse --verify 'HEAD^{commit}')"
    must "starting-os-ref-is-exact" "$os_start_head/$from_os_ref" \
        test "$os_start_head" = "$from_os_ref"
    must "starting-kilix95-ref-is-exact" "$kilix95_start_head/$from_kilix95_ref" \
        test "$kilix95_start_head" = "$from_kilix95_ref"
fi

"$pleb_bin" update --help >"$report/pleb-update-help.txt" 2>&1
must "installed-entrypoint-supports-named-hop" "pleb update --to" \
    grep -q -- '--to X.Y.Z' "$report/pleb-update-help.txt"
"$pleb_bin" update --show >"$report/show-before.txt" 2>"$report/show-before.stderr"
current="$(sed -n 's/^  PLEBIAN_OS_VERSION=\([^ ]*\).*/\1/p' "$report/show-before.txt" | head -n 1)"
[[ "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "could not resolve the installed release from pleb update --show"
must "starting-release-is-exact" "$current/$from" test "$current" = "$from"
must "target-differs-from-installed-release" "$current -> $target" test "$current" != "$target"

session_before="$(path_fingerprint "$session_env")"
closure_before="$(path_fingerprint "$closure_env")"
settings_file="${GPU_TERMINAL_SETTINGS_FILE:-${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}/settings.conf}"
engine_current="${KILIX_STATE_DIRECTORY:-${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}/kilix/state}/current"
settings_before="$(path_fingerprint "$settings_file")"
engine_before="$(path_fingerprint "$engine_current")"
printf '%s\n' "$session_before" >"$report/session.before"
printf '%s\n' "$closure_before" >"$report/closure.before"
printf '%s\n' "$settings_before" >"$report/settings.before"
printf '%s\n' "$engine_before" >"$report/engine.before"

git_snapshot "$pleb_dir" pleb-before-dry-run
git_snapshot "$kilix_dir" kilix-before-dry-run
set +e
"$pleb_bin" update --to "$target" --dry-run --yes --no-restart \
    >"$report/dry-run.stdout" 2>"$report/dry-run.stderr"
dry_run_rc=$?
set -e
printf '%s\n' "$dry_run_rc" >"$report/dry-run.exit"
must "target-dry-run-succeeds-before-mutation" \
    "pleb update --to $target --dry-run; exit=$dry_run_rc" test "$dry_run_rc" -eq 0
git_snapshot "$pleb_dir" pleb-after-dry-run
git_snapshot "$kilix_dir" kilix-after-dry-run
must "dry-run-preserves-pleb-head" "1/1" \
    cmp -s "$report/pleb-before-dry-run.head" "$report/pleb-after-dry-run.head"
must "dry-run-preserves-pleb-status" "1/1" \
    cmp -s "$report/pleb-before-dry-run.status" "$report/pleb-after-dry-run.status"
must "dry-run-preserves-kilix-head" "1/1" \
    cmp -s "$report/kilix-before-dry-run.head" "$report/kilix-after-dry-run.head"
must "dry-run-preserves-kilix-status" "1/1" \
    cmp -s "$report/kilix-before-dry-run.status" "$report/kilix-after-dry-run.status"
must "dry-run-preserves-session-env" "$session_env" \
    test "$(path_fingerprint "$session_env")" = "$session_before"
must "dry-run-preserves-closure-env" "$closure_env" \
    test "$(path_fingerprint "$closure_env")" = "$closure_before"
must "dry-run-preserves-settings" "$settings_file" \
    test "$(path_fingerprint "$settings_file")" = "$settings_before"
must "dry-run-preserves-engine-generation" "$engine_current" \
    test "$(path_fingerprint "$engine_current")" = "$engine_before"

sentinels="$report/sentinels.tsv"
: >"$sentinels"
for camera in backdrivecam drivecam g2 garage gazebo poolcam tapo; do
    path="$pleb_dir/scripts/f109-qualification-camera-$camera.sh"
    if [ -e "$path" ] || [ -L "$path" ]; then
        die "sentinel path already exists: $path"
    fi
    printf '#!/usr/bin/env bash\nprintf "%%s\\n" "f109-%s"\n' "$camera" >"$path"
    chmod 0700 "$path"
    printf '%s\t%s\tuntracked\n' "$path" "$(sha256sum "$path" | awk '{print $1}')" >>"$sentinels"
done
kilix_sentinel="$kilix_dir/f109-qualification-operator.bin"
if [ -e "$kilix_sentinel" ] || [ -L "$kilix_sentinel" ]; then
    die "sentinel path already exists: $kilix_sentinel"
fi
printf '\000F109-operator-state\377\n' >"$kilix_sentinel"
chmod 0600 "$kilix_sentinel"
printf '%s\t%s\tuntracked\n' "$kilix_sentinel" \
    "$(sha256sum "$kilix_sentinel" | awk '{print $1}')" >>"$sentinels"

for item in "$pleb_dir/README.md:pleb" "$kilix_dir/README.md:kilix"; do
    path="${item%:*}"; label="${item##*:}"
    git -C "$(dirname "$path")" ls-files --error-unmatch "$(basename "$path")" >/dev/null \
        || die "tracked sentinel fixture is missing: $path"
    if [ -e "$path.local" ] || [ -L "$path.local" ]; then
        die "tracked sentinel recovery path already exists: $path.local"
    fi
    printf '\nF109-QUALIFICATION-%s-LOCAL\n' "$label" >>"$path"
    printf '%s\t%s\tmodified-tracked\n' "$path" \
        "$(sha256sum "$path" | awk '{print $1}')" >>"$sentinels"
done

app_state="${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}/f109-qualification-app-state"
[ ! -e "$app_state" ] || die "application sentinel path already exists: $app_state"
mkdir -p -- "$app_state"
printf '{"schema":"kilix.install.license/v1","qualification":true}\n' >"$app_state/license-receipt.json"
printf 'f109-installed-asset\n' >"$app_state/installed-asset"
printf 'f109-catalog-snapshot\n' >"$app_state/catalog-snapshot"
find "$app_state" -type f -print0 | sort -z | while IFS= read -r -d '' path; do
    printf '%s\t%s\tapplication-state\n' "$path" \
        "$(sha256sum "$path" | awk '{print $1}')" >>"$sentinels"
done
sentinel_declared="$(wc -l <"$sentinels")"
must "declared-sentinel-corpus-is-complete" "$sentinel_declared/13" \
    test "$sentinel_declared" -eq 13

git_snapshot "$pleb_dir" pleb-before
git_snapshot "$kilix_dir" kilix-before
home_manifest "$report/home-before.tsv"

failure_boundary=closure
set +e
PLEBIAN_OS_SELECT_TEST_FAIL_AFTER="$failure_boundary" \
    "$pleb_bin" update --to "$target" --yes --no-restart \
    >"$report/induced-failure.stdout" 2>"$report/induced-failure.stderr"
failure_rc=$?
set -e
printf '%s\n' "$failure_rc" >"$report/induced-failure.exit"
must "induced-hop-fails" "boundary=$failure_boundary exit=$failure_rc" test "$failure_rc" -ne 0
git_snapshot "$pleb_dir" pleb-after-failure
git_snapshot "$kilix_dir" kilix-after-failure
must "failure-restores-pleb-head" "1/1" cmp -s "$report/pleb-before.head" "$report/pleb-after-failure.head"
must "failure-restores-pleb-status" "1/1" cmp -s "$report/pleb-before.status" "$report/pleb-after-failure.status"
must "failure-restores-kilix-head" "1/1" cmp -s "$report/kilix-before.head" "$report/kilix-after-failure.head"
must "failure-restores-kilix-status" "1/1" cmp -s "$report/kilix-before.status" "$report/kilix-after-failure.status"
must "failure-restores-session-env" "$session_env" test "$(path_fingerprint "$session_env")" = "$session_before"
must "failure-restores-closure-env" "$closure_env" test "$(path_fingerprint "$closure_env")" = "$closure_before"
must "failure-restores-settings" "$settings_file" \
    test "$(path_fingerprint "$settings_file")" = "$settings_before"
must "failure-restores-engine-generation" "$engine_current" \
    test "$(path_fingerprint "$engine_current")" = "$engine_before"
home_manifest "$report/home-after-failure.tsv"
diff -u "$report/home-before.tsv" "$report/home-after-failure.tsv" \
    >"$report/home-induced-failure.diff" || true

"$pleb_bin" update --to "$target" --yes --no-restart \
    >"$report/success.stdout" 2>"$report/success.stderr"
success_rc=$?
printf '%s\n' "$success_rc" >"$report/success.exit"
must "single-command-hop-succeeds" "pleb update --to $target; exit=$success_rc" test "$success_rc" -eq 0
"$pleb_bin" update --show >"$report/show-after.txt" 2>"$report/show-after.stderr"
selected="$(sed -n 's/^  PLEBIAN_OS_VERSION=\([^ ]*\).*/\1/p' "$report/show-after.txt" | head -n 1)"
must "selected-release-is-target" "$selected/$target" test "$selected" = "$target"

sentinel_total=0
sentinel_pass=0
while IFS=$'\t' read -r path expected kind; do
    sentinel_total=$((sentinel_total + 1))
    actual_path="$path"
    if [ "$kind" = modified-tracked ]; then actual_path="$path.local"; fi
    if [ -f "$actual_path" ] \
        && [ "$(sha256sum "$actual_path" | awk '{print $1}')" = "$expected" ]; then
        sentinel_pass=$((sentinel_pass + 1))
    else
        die "sentinel did not survive byte-identically: $actual_path"
    fi
done <"$sentinels"
record_check "all-sentinels-byte-identical" pass "$sentinel_pass/$sentinel_total"
must "all-13-sentinels-are-accounted-for" "$sentinel_pass/$sentinel_total" \
    test "$sentinel_pass" -eq 13 -a "$sentinel_total" -eq 13
must "successful-hop-preserves-settings" "$settings_file" \
    test "$(path_fingerprint "$settings_file")" = "$settings_before"

preserve_root="${PLEB_STATE_HOME:-$HOME/.local/gpu_terminal/pleb/state}/update-preserve"
mapfile -t preservation_manifests < <(find "$preserve_root" -type f -name MANIFEST.sha256 -print 2>/dev/null | sort)
[ "${#preservation_manifests[@]}" -gt 0 ] \
    || die "no checksummed preservation records were produced"
preservation_pass=0
for manifest in "${preservation_manifests[@]}"; do
    if (cd "$(dirname "$manifest")" && sha256sum -c MANIFEST.sha256 >/dev/null); then
        preservation_pass=$((preservation_pass + 1))
    else
        die "preservation checksum failed: $manifest"
    fi
done
record_check "preservation-manifests-verify" pass \
    "$preservation_pass/${#preservation_manifests[@]}"

if [ "$shape" = standalone ]; then
    must "standalone-still-has-no-system-session" "/etc/pleb/session.env" test ! -e /etc/pleb/session.env
    must "standalone-still-has-no-os-source" "$source_home/plebian-os" test ! -e "$source_home/plebian-os"
    must "standalone-still-has-no-os-updater" "/usr/local/bin/plebian-os-update" test ! -e /usr/local/bin/plebian-os-update
fi

home_manifest "$report/home-after-success.tsv"
diff -u "$report/home-before.tsv" "$report/home-after-success.tsv" \
    >"$report/home-success.diff" || true
git_snapshot "$pleb_dir" pleb-after-success
git_snapshot "$kilix_dir" kilix-after-success
record_check "evidence-artifacts-written" pass "home manifests 3/3; hop logs 2/2"

export F109_REPORT_SHAPE="$shape" F109_REPORT_TARGET="$target"
export F109_REPORT_CURRENT="$current" F109_REPORT_VIRT="$virt"
export F109_REPORT_FROM_PLEB_REF="$from_pleb_ref"
export F109_REPORT_FROM_KILIX_REF="$from_kilix_ref"
export F109_REPORT_FROM_OS_REF="$from_os_ref"
export F109_REPORT_FROM_KILIX95_REF="$from_kilix95_ref"
export F109_REPORT_BUILD_INFO_SHA256="$expected_build_info_sha256"
export F109_REPORT_CHECK_PASS="$check_pass" F109_REPORT_CHECK_TOTAL="$check_total"
export F109_REPORT_SENTINEL_PASS="$sentinel_pass" F109_REPORT_SENTINEL_TOTAL="$sentinel_total"
export F109_REPORT_PRESERVE_PASS="$preservation_pass"
export F109_REPORT_PRESERVE_TOTAL="${#preservation_manifests[@]}"
F109_REPORT_PLEB_HEAD="$(cat "$report/pleb-after-success.head")"
F109_REPORT_KILIX_HEAD="$(cat "$report/kilix-after-success.head")"
export F109_REPORT_PLEB_HEAD F109_REPORT_KILIX_HEAD
python3 - "$report/report.json" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

def integer(name):
    return int(os.environ[name])

report = {
    "schema": "plebian-os.f109-release-hop-acceptance/v1",
    "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": "pass",
    "measured_not_adjudicated": True,
    "shape": os.environ["F109_REPORT_SHAPE"],
    "virtualization": os.environ["F109_REPORT_VIRT"],
    "release_hop": {
        "from": os.environ["F109_REPORT_CURRENT"],
        "to": os.environ["F109_REPORT_TARGET"],
        "dry_run_commands": 1,
        "dry_run_command_denominator": 1,
        "successful_hop_commands": 1,
        "successful_hop_command_denominator": 1,
    },
    "starting_fixture": {
        "pleb_ref": os.environ["F109_REPORT_FROM_PLEB_REF"],
        "kilix_ref": os.environ["F109_REPORT_FROM_KILIX_REF"],
        "plebian_os_ref": os.environ["F109_REPORT_FROM_OS_REF"] or None,
        "kilix95_ref": os.environ["F109_REPORT_FROM_KILIX95_REF"] or None,
        "installed_build_info_sha256": (
            os.environ["F109_REPORT_BUILD_INFO_SHA256"] or None
        ),
    },
    "candidate_heads": {
        "pleb": os.environ["F109_REPORT_PLEB_HEAD"],
        "kilix": os.environ["F109_REPORT_KILIX_HEAD"],
    },
    "checks": {
        "passed": integer("F109_REPORT_CHECK_PASS"),
        "total": integer("F109_REPORT_CHECK_TOTAL"),
    },
    "sentinels": {
        "byte_identical": integer("F109_REPORT_SENTINEL_PASS"),
        "total": integer("F109_REPORT_SENTINEL_TOTAL"),
    },
    "preservation_manifests": {
        "verified": integer("F109_REPORT_PRESERVE_PASS"),
        "total": integer("F109_REPORT_PRESERVE_TOTAL"),
    },
    "artifacts": {
        "home_before": "home-before.tsv",
        "home_after_induced_failure": "home-after-failure.tsv",
        "home_after_success": "home-after-success.tsv",
        "home_success_diff": "home-success.diff",
        "dry_run_stdout": "dry-run.stdout",
        "dry_run_stderr": "dry-run.stderr",
        "checks": "checks.tsv",
        "sentinels": "sentinels.tsv",
    },
}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

sums_tmp="$report/.SHA256SUMS.tmp"
(
    cd "$report"
    find . -maxdepth 1 -type f ! -name SHA256SUMS \
        ! -name '.SHA256SUMS.tmp' -printf '%P\0' \
        | sort -z | xargs -0 sha256sum
) >"$sums_tmp"
mv -fT -- "$sums_tmp" "$report/SHA256SUMS"
(
    cd "$report"
    sha256sum -c SHA256SUMS >/dev/null
)
evidence_count="$(wc -l <"$report/SHA256SUMS")"
printf 'acceptance-release-hop: PASS %s -> %s (%s); checks %s/%s; evidence checksums %s/%s at %s\n' \
    "$current" "$target" "$shape" "$check_pass" "$check_total" \
    "$evidence_count" "$evidence_count" "$report"
