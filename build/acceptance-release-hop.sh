#!/usr/bin/env bash
# acceptance-release-hop.sh — F109's two-shape, real-guest release-hop lane.
#
# Run this only inside a disposable VM whose installed closure is the accepted
# previous release.  The runner plants checkout and application-state
# sentinels, induces one selector-transaction failure, proves compensation,
# performs the successful hop with one `pleb update --to` command, and emits a
# checksummed evidence directory.  It deliberately does not create tags or a
# release manifest: those are release-owner inputs, not qualification output.
# The image lane proves the documented dirty-checkout refusal, then explicitly
# moves its ten checkout fixtures aside with checksums before the clean hop.
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
image_operator_files=0
declare -A image_resolved_paths=()

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
[ "$EUID" -ne 0 ] || die "run qualification as the installed Pleb user, without sudo"
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
pleb_dir="$(cd "$pleb_dir" && pwd -P)"
[ -d "$pleb_dir/.git" ] || die "Pleb is not a git checkout: $pleb_dir"

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

engine_fingerprint() {
    local build_dir="$1" state_dir="$2" selector payload
    for selector in current previous; do
        printf '%s\t' "$selector"
        path_fingerprint "$build_dir/$selector"
        for payload in source-id src/kitty/launcher/kitty src/kitty/launcher/kitten; do
            printf '%s/%s\t' "$selector" "$payload"
            path_fingerprint "$build_dir/$selector/$payload"
        done
    done
    printf 'fork-built-ref\t'
    path_fingerprint "$state_dir/fork-built-ref"
}

# Use the installed CLI's resolver, including its config precedence and root
# safety checks. Keep config shell code in a same-user subprocess so it cannot
# overwrite qualification variables. No exported/default-only fallback is safe.
resolve_installed_paths() {
    local code_root="$1"
    [ -f "$code_root/lib/common.sh" ] || return 1
    bash -euo pipefail -c '
        PLEB_ROOT="$1"
        . "$PLEB_ROOT/lib/common.sh" >&2
        names=(KILIX_BUILD_DIRECTORY KILIX_STATE_DIRECTORY GPU_TERMINAL_SETTINGS_FILE
               GPU_TERMINAL_SOURCE_HOME PLEB_STATE_HOME PLEB_ENV_SYSTEM PLEB_ENV_USER
               PLEB_CLOSURE_SYSTEM PLEB_CLOSURE_USER KILIX_DIR PLEB_DIR KILIX_PREBUILT_HOME)
        for name in "${names[@]}"; do
            value="${!name}"
            case "$value" in
                *$'"'"'\n'"'"'*|*$'"'"'\r'"'"'*|*$'"'"'\t'"'"'*) exit 1 ;;
            esac
            case "$value" in
                /*) ;;
                "") case "$name" in
                    PLEB_ENV_SYSTEM|PLEB_ENV_USER|PLEB_CLOSURE_SYSTEM|PLEB_CLOSURE_USER) ;;
                    *) exit 1 ;;
                    esac ;;
                *) exit 1 ;;
            esac
            printf "%s\n" "$value"
        done
    ' bash "$code_root"
}

select_installed_paths() {
    local -a values
    installed_paths="$(resolve_installed_paths "$pleb_dir")" || return 1
    mapfile -t values <<<"$installed_paths"
    [ "${#values[@]}" -eq 12 ] || return 1
    engine_build="${values[0]}"; engine_state="${values[1]}"
    settings_file="${values[2]}"; source_home="${values[3]}"
    preserve_root="${values[4]}/update-preserve"
    installed_system_session="${values[5]}"; installed_user_session="${values[6]}"
    installed_system_closure="${values[7]}"; installed_user_closure="${values[8]}"
    installed_kilix_dir="${values[9]}"; installed_pleb_dir="${values[10]}"
    engine_prebuilt="${values[11]}"
}

bound_engine_fingerprint() {
    local actual payload path
    actual="$(resolve_installed_paths "$pleb_dir")" || return 1
    [ "$actual" = "$installed_paths" ] || {
        printf '%s\n' 'acceptance-release-hop: effective installed paths changed' >&2
        return 1
    }
    engine_fingerprint "$engine_build" "$engine_state"
    for payload in kitty kitten; do
        path="$engine_prebuilt/bin/$payload"
        printf 'prebuilt-%s\t' "$payload"; path_fingerprint "$path"
        if [ -L "$path" ] && [ -f "$path" ]; then
            printf 'prebuilt-%s-target\t' "$payload"
            sha256sum -- "$path" | cut -d ' ' -f 1 || return 1
        fi
    done
}

verify_installed_target_ref() {
    local component="$1" checkout_dir="$2" selected_ref="$3" installed_ref
    [[ "$selected_ref" =~ ^[0-9a-f]{40}$ ]] \
        || die "selected $component ref is not an exact commit"
    installed_ref="$(git -C "$checkout_dir" rev-parse --verify HEAD)"
    must "installed-$component-ref-matches-target" "$installed_ref/$selected_ref" \
        test "$installed_ref" = "$selected_ref"
}

# Freeze the successful guest state for the host controller's post-reboot check.
# Shell quoting binds literal paths/values; no guest input is evaluated as code.
write_reboot_verifier() {
    local output="$1" component ref_key checkout_dir selected_ref path expected kind actual_path
    {
        printf '#!/usr/bin/env bash\nset -euo pipefail\n'
        declare -f path_fingerprint engine_fingerprint resolve_installed_paths bound_engine_fingerprint
        printf 'pleb_dir=%q; installed_paths=%q; engine_build=%q; engine_state=%q; engine_prebuilt=%q\n' \
            "$pleb_dir" "$installed_paths" "$engine_build" "$engine_state" "$engine_prebuilt"
        printf 'test "$(cat /etc/machine-id)" = %q\n' "$(cat /etc/machine-id)"
        printf 'test "$(%q update --show)" = %q\n' "$pleb_bin" "$(cat "$report/show-after.txt")"
        for component in "${target_components[@]}"; do
            case "$component" in
                pleb) ref_key=PLEB_REF; checkout_dir="$pleb_dir" ;;
                kilix) ref_key=KILIX_REF; checkout_dir="$kilix_dir" ;;
                os) ref_key=PLEBIAN_OS_REF; checkout_dir="$os_dir" ;;
                kilix95) ref_key=KILIX95_REF; checkout_dir="$kilix95_dir" ;;
            esac
            selected_ref="$(sed -n "s/^  $ref_key=\([^ ]*\).*/\1/p" "$report/show-after.txt" | head -n 1)"
            [[ "$selected_ref" =~ ^[0-9a-f]{40}$ ]] || return 1
            printf 'test "$(git -C %q rev-parse --verify HEAD)" = %q\n' "$checkout_dir" "$selected_ref"
        done
        for path in "$session_env" "$closure_env" "$settings_file"; do
            printf 'test "$(path_fingerprint %q)" = %q\n' "$path" "$(path_fingerprint "$path")"
        done
        printf 'actual_engine="$(bound_engine_fingerprint)"\ntest "$actual_engine" = %q\n' \
            "$(bound_engine_fingerprint)"
        while IFS=$'\t' read -r path expected kind; do
            if [ -n "${image_resolved_paths[$path]:-}" ]; then
                actual_path="${image_resolved_paths[$path]}"
            else
                actual_path="$(preserved_sentinel_path "$path" "$expected" "$kind")" || return 1
            fi
            printf 'test -f %q && test ! -L %q\n' "$actual_path" "$actual_path"
            printf 'test "$(sha256sum -- %q | cut -d " " -f 1)" = %q\n' "$actual_path" "$expected"
        done <"$sentinels"
    } >"$output"
}

preserved_sentinel_path() {
    local path="$1" expected="$2" kind="$3" candidate
    local -a candidates=("$path")
    if [ "$kind" = modified-tracked ]; then
        candidates+=("$path.local" "$path.local."*)
    fi
    for candidate in "${candidates[@]}"; do
        [ -f "$candidate" ] && [ ! -L "$candidate" ] || continue
        if [ "$(sha256sum -- "$candidate" | awk '{print $1}')" = "$expected" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

resolve_image_checkout_fixtures() {
    local path expected kind repo relative saved count=0
    case "$report/" in "$pleb_dir/"*|"$kilix_dir/"*)
        die "operator resolution must be outside participating checkouts" ;;
    esac
    : >"$report/operator-resolution.tsv"
    : >"$report/OPERATOR-RESOLUTION.sha256"
    while IFS=$'\t' read -r path expected kind; do
        case "$kind" in untracked|modified-tracked) ;; *) continue ;; esac
        case "$path" in
            "$pleb_dir/"*) repo="$pleb_dir"; relative="pleb/${path#"$pleb_dir/"}" ;;
            "$kilix_dir/"*) repo="$kilix_dir"; relative="kilix/${path#"$kilix_dir/"}" ;;
            *) die "checkout fixture lies outside participating checkouts: $path" ;;
        esac
        [ -f "$path" ] && [ ! -L "$path" ] || die "unsafe checkout fixture: $path"
        saved="$report/operator-resolved-${relative//\//--}"
        [ ! -e "$saved" ] && [ ! -L "$saved" ] || die "operator recovery path exists: $saved"
        cp -p -- "$path" "$saved"
        [ "$(sha256sum -- "$saved" | awk '{print $1}')" = "$expected" ] \
            || die "operator move-aside verification failed: $path"
        sync -f "$saved"
        printf '%s\t%s\t%s\t%s\n' "$path" "$saved" "$expected" "$kind" \
            >>"$report/operator-resolution.tsv"
        printf '%s  %s\n' "$expected" "${saved#"$report/"}" \
            >>"$report/OPERATOR-RESOLUTION.sha256"
        count=$((count + 1))
    done <"$sentinels"
    [ "$count" = 10 ] || die "operator move-aside requires all ten checkout fixtures"
    sync -f "$report/operator-resolution.tsv"
    sync -f "$report/OPERATOR-RESOLUTION.sha256"
    sync -f "$report"
    while IFS=$'\t' read -r path saved expected kind; do
        [ "$(sha256sum -- "$path" | awk '{print $1}')" = "$expected" ] \
            || die "checkout fixture changed before operator move-aside: $path"
        mv -- "$path" "$saved"
        image_resolved_paths["$path"]="$saved"
        if [ "$kind" = modified-tracked ]; then
            case "$path" in "$pleb_dir/"*) repo="$pleb_dir" ;; *) repo="$kilix_dir" ;; esac
            git -C "$repo" restore --source=HEAD --worktree -- "${path#"$repo/"}"
        fi
    done <"$report/operator-resolution.tsv"
    (cd "$report" && sha256sum -c OPERATOR-RESOLUTION.sha256)
    image_operator_files="$count"
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
select_installed_paths || die "could not bind effective installed paths using Pleb's resolver"
printf '%s\n' "$installed_paths" >"$report/installed-paths.before"
must "resolver-matches-participating-pleb-checkout" "$installed_pleb_dir" \
    test "$(cd "$installed_pleb_dir" && pwd -P)" = "$pleb_dir"
if [ -z "$kilix_dir" ]; then kilix_dir="$installed_kilix_dir"; fi
kilix_dir="$(cd "$kilix_dir" && pwd -P)"
must "resolver-matches-participating-kilix-checkout" "$installed_kilix_dir" \
    test "$(cd "$installed_kilix_dir" && pwd -P)" = "$kilix_dir"
[ -d "$kilix_dir/.git" ] || die "Kilix is not a git checkout: $kilix_dir"
if [ "$shape" = image ]; then
    installed_session="$installed_system_session"; installed_closure="$installed_system_closure"
else
    installed_session="$installed_user_session"; installed_closure="$installed_user_closure"
fi
if [ -z "$session_env" ]; then session_env="$installed_session"; fi
if [ -z "$closure_env" ]; then closure_env="$installed_closure"; fi
must "session-path-is-bound-to-installed-config" "$session_env" test "$session_env" = "$installed_session"
must "closure-path-is-bound-to-installed-config" "$closure_env" test "$closure_env" = "$installed_closure"
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
settings_before="$(path_fingerprint "$settings_file")"
engine_before="$(bound_engine_fingerprint)"
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
must "dry-run-preserves-engine-generation" "$engine_build" \
    test "$(bound_engine_fingerprint)" = "$engine_before"

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

if [ "$shape" = image ]; then
    printf 'Image checkout policy: proving refusal, then checksummed operator move-aside per UPGRADING.md.\n'
    selector_before="$(path_fingerprint /usr/local/bin/plebian-os-select-closure)"
    updater_before="$(path_fingerprint /usr/local/bin/plebian-os-update)"
    git_snapshot "$os_dir" os-before-dirty-refusal
    git_snapshot "$kilix95_dir" kilix95-before-dirty-refusal
    set +e
    "$pleb_bin" update --to "$target" --yes --no-restart \
        >"$report/dirty-refusal.stdout" 2>"$report/dirty-refusal.stderr"
    dirty_rc=$?
    set -e
    printf '%s\n' "$dirty_rc" >"$report/dirty-refusal.exit"
    must "dirty-image-hop-refuses" "exit=$dirty_rc" test "$dirty_rc" -ne 0
    must "dirty-image-refusal-is-the-cleanliness-guard" "whole-stack guard" \
        grep -q 'has local changes; refusing a whole-stack update' "$report/dirty-refusal.stderr"
    for component in pleb kilix os kilix95; do
        case "$component" in
            pleb) checkout_dir="$pleb_dir"; before_prefix=pleb-before ;;
            kilix) checkout_dir="$kilix_dir"; before_prefix=kilix-before ;;
            os) checkout_dir="$os_dir"; before_prefix=os-before-dirty-refusal ;;
            kilix95) checkout_dir="$kilix95_dir"; before_prefix=kilix95-before-dirty-refusal ;;
        esac
        git_snapshot "$checkout_dir" "$component-after-dirty-refusal"
        for field in head status; do
            must "dirty-refusal-preserves-$component-$field" "1/1" \
                cmp -s "$report/$before_prefix.$field" "$report/$component-after-dirty-refusal.$field"
        done
    done
    for item in session closure settings engine selector updater; do
        case "$item" in
            session) path="$session_env"; expected="$session_before" ;;
            closure) path="$closure_env"; expected="$closure_before" ;;
            settings) path="$settings_file"; expected="$settings_before" ;;
            engine)
                must "dirty-refusal-preserves-engine" "$engine_build" \
                    test "$(bound_engine_fingerprint)" = "$engine_before"
                continue ;;
            selector) path=/usr/local/bin/plebian-os-select-closure; expected="$selector_before" ;;
            updater) path=/usr/local/bin/plebian-os-update; expected="$updater_before" ;;
        esac
        must "dirty-refusal-preserves-$item" "$path" test "$(path_fingerprint "$path")" = "$expected"
    done
    while IFS=$'\t' read -r path expected kind; do
        must "dirty-refusal-preserves-sentinel" "$path" \
            test "$(sha256sum -- "$path" | awk '{print $1}')" = "$expected"
    done <"$sentinels"
    must "dirty-refusal-clears-incomplete-transition" "selection never advanced" \
        test ! -e "${PLEB_STATE_HOME:-$HOME/.local/gpu_terminal/pleb/state}/release-hop/active"
    resolve_image_checkout_fixtures
    must "image-operator-move-aside-is-complete" "$image_operator_files/10" \
        test "$image_operator_files" -eq 10
    must "image-pleb-checkout-resolved-clean" "$pleb_dir" test -z \
        "$(git -C "$pleb_dir" status --porcelain=v1 --untracked-files=all)"
    must "image-kilix-checkout-resolved-clean" "$kilix_dir" test -z \
        "$(git -C "$kilix_dir" status --porcelain=v1 --untracked-files=all)"
fi
git_snapshot "$pleb_dir" pleb-before-failure
git_snapshot "$kilix_dir" kilix-before-failure
home_manifest "$report/home-before-failure.tsv"

failure_boundary=closure
set +e
PLEBIAN_OS_SELECT_TEST_FAIL_AFTER="$failure_boundary" \
    "$pleb_bin" update --to "$target" --yes --no-restart \
    >"$report/induced-failure.stdout" 2>"$report/induced-failure.stderr"
failure_rc=$?
set -e
printf '%s\n' "$failure_rc" >"$report/induced-failure.exit"
must "induced-hop-fails" "boundary=$failure_boundary exit=$failure_rc" test "$failure_rc" -ne 0
must "induced-closure-boundary-was-reached" "$failure_boundary" \
    grep -q 'injected split-closure failure' "$report/induced-failure.stderr"
git_snapshot "$pleb_dir" pleb-after-failure
git_snapshot "$kilix_dir" kilix-after-failure
must "failure-restores-pleb-head" "1/1" cmp -s "$report/pleb-before-failure.head" "$report/pleb-after-failure.head"
must "failure-restores-pleb-status" "1/1" cmp -s "$report/pleb-before-failure.status" "$report/pleb-after-failure.status"
must "failure-restores-kilix-head" "1/1" cmp -s "$report/kilix-before-failure.head" "$report/kilix-after-failure.head"
must "failure-restores-kilix-status" "1/1" cmp -s "$report/kilix-before-failure.status" "$report/kilix-after-failure.status"
must "failure-restores-session-env" "$session_env" test "$(path_fingerprint "$session_env")" = "$session_before"
must "failure-restores-closure-env" "$closure_env" test "$(path_fingerprint "$closure_env")" = "$closure_before"
must "failure-restores-settings" "$settings_file" \
    test "$(path_fingerprint "$settings_file")" = "$settings_before"
must "failure-restores-engine-generation" "$engine_build" \
    test "$(bound_engine_fingerprint)" = "$engine_before"
home_manifest "$report/home-after-failure.tsv"
diff -u "$report/home-before-failure.tsv" "$report/home-after-failure.tsv" \
    >"$report/home-induced-failure.diff" || true

set +e
"$pleb_bin" update --to "$target" --yes --no-restart \
    >"$report/success.stdout" 2>"$report/success.stderr"
success_rc=$?
set -e
printf '%s\n' "$success_rc" >"$report/success.exit"
must "single-command-hop-succeeds" "pleb update --to $target; exit=$success_rc" test "$success_rc" -eq 0
"$pleb_bin" update --show >"$report/show-after.txt" 2>"$report/show-after.stderr"
selected="$(sed -n 's/^  PLEBIAN_OS_VERSION=\([^ ]*\).*/\1/p' "$report/show-after.txt" | head -n 1)"
must "selected-release-is-target" "$selected/$target" test "$selected" = "$target"
target_components=(pleb kilix)
if [ "$shape" = image ]; then target_components+=(os kilix95); fi
for component in "${target_components[@]}"; do
    case "$component" in
        pleb) ref_key=PLEB_REF; checkout_dir="$pleb_dir" ;;
        kilix) ref_key=KILIX_REF; checkout_dir="$kilix_dir" ;;
        os) ref_key=PLEBIAN_OS_REF; checkout_dir="$os_dir" ;;
        kilix95) ref_key=KILIX95_REF; checkout_dir="$kilix95_dir" ;;
    esac
    selected_ref="$(sed -n "s/^  $ref_key=\\([^ ]*\\).*/\\1/p" "$report/show-after.txt" | head -n 1)"
    verify_installed_target_ref "$component" "$checkout_dir" "$selected_ref"
done

sentinel_total=0
sentinel_pass=0
: >"$report/sentinel-locations.tsv"
while IFS=$'\t' read -r path expected kind; do
    sentinel_total=$((sentinel_total + 1))
    if [ -n "${image_resolved_paths[$path]:-}" ]; then
        actual_path="${image_resolved_paths[$path]}"
        test "$(sha256sum -- "$actual_path" | awk '{print $1}')" = "$expected" \
            || die "operator-resolved sentinel changed: $actual_path"
        sentinel_pass=$((sentinel_pass + 1))
        printf '%s\t%s\n' "$path" "$actual_path" >>"$report/sentinel-locations.tsv"
    elif actual_path="$(preserved_sentinel_path "$path" "$expected" "$kind")"; then
        sentinel_pass=$((sentinel_pass + 1))
        printf '%s\t%s\n' "$path" "$actual_path" >>"$report/sentinel-locations.tsv"
    else
        die "sentinel did not survive byte-identically at its original or recovery path: $path"
    fi
done <"$sentinels"
record_check "all-sentinels-byte-identical" pass "$sentinel_pass/$sentinel_total"
must "all-13-sentinels-are-accounted-for" "$sentinel_pass/$sentinel_total" \
    test "$sentinel_pass" -eq 13 -a "$sentinel_total" -eq 13
must "successful-hop-preserves-settings" "$settings_file" \
    test "$(path_fingerprint "$settings_file")" = "$settings_before"

preservation_manifests=()
if [ "$shape" = standalone ]; then
    mapfile -t preservation_manifests < <(find "$preserve_root" -type f -name MANIFEST.sha256 -print 2>/dev/null | sort)
    [ "${#preservation_manifests[@]}" -gt 0 ] \
        || die "no checksummed automatic preservation records were produced"
fi
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


write_reboot_verifier "$report/verify-after-reboot.sh" \
    || die "could not bind the post-reboot verifier"
must "post-reboot-verifier-matches-successful-state" "exact closure, installed refs, engine and sentinels" \
    bash "$report/verify-after-reboot.sh"

home_manifest "$report/home-after-success.tsv"
diff -u "$report/home-before.tsv" "$report/home-after-success.tsv" \
    >"$report/home-success.diff" || true
git_snapshot "$pleb_dir" pleb-after-success
git_snapshot "$kilix_dir" kilix-after-success
record_check "evidence-artifacts-written" pass "home manifests 4/4; failure/success hop logs 2/2"

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
export F109_REPORT_OPERATOR_FILES="$image_operator_files"
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
        "dirty_preflight_refusal_commands": int(os.environ["F109_REPORT_SHAPE"] == "image"),
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
    "operator_checkout_resolution": {
        "required": os.environ["F109_REPORT_SHAPE"] == "image",
        "files_moved_aside": integer("F109_REPORT_OPERATOR_FILES"),
        "automatic_preservation_claimed": False,
        "manifest": "OPERATOR-RESOLUTION.sha256" if integer("F109_REPORT_OPERATOR_FILES") else None,
        "locations": "operator-resolution.tsv" if integer("F109_REPORT_OPERATOR_FILES") else None,
    },
    "artifacts": {
        "home_before": "home-before.tsv",
        "home_before_induced_failure": "home-before-failure.tsv",
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
