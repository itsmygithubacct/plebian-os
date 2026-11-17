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

Optional --bootstrap-driver PATH --bootstrap-driver-ref SHA uses an explicit
legacy migration driver without replacing the installed CLI before the hop.
A same-version hop is accepted only as --from X.Y.Z --target X.Y.Z
--release-tag vX.Y.Z --from-release-tag vX.Y.Z-rcN
--from-release-tag-object SHA --release-tag-object SHA
--expected-release-commit SHA --from-release-manifest FILE. It uses the
installed CLI. The guest reads the installed RC from the closure, shell-sourced,
and checks it against pleb update --show and the published RC manifest. An
image guest with no closure.env is accepted only when its build-info bytes
equal the source ISO. Release-mode show resolves PLEBIAN_OS_REF from
session.env, which stores the commit, while that build-info stores the RC
tag; the commit in the build-info peels the tag. Rollback compares session,
closure, settings, the selector and updater, the engine generation, and every
component checkout HEAD with their pre-hop state, and requires that no
release-hop record (active, phase, baseline, unselected-checkouts) is left: Pleb keeps one generation
of rollback, so a record from an earlier completed hop is replaced when the hop
starts and is not restored. A fresh image has no closure
to compare byte for byte, so that check is not recorded. Image recovery
records are read with sudo -n. A selection_tag= value must equal
--from-release-tag-object. A record that still cannot be read is unreadable
and not-verified, not a pass. The hop then runs again and those same paths
must match the post-hop record. No bootstrap driver is accepted. The guest
must start on the accepted previous release.
DIR must be outside $HOME. Image guests require the build-info options,
including --predecessor-build-info-sha256 for an upgraded install. The
command refuses non-VM hosts, a dirty source checkout, or a starting
closure mismatch.
EOF
}

die() {
    printf 'acceptance-release-hop: %s\n' "$*" >&2
    exit 1
}

shape=""
from=""
target=""
release_tag=""
from_release_tag=""
from_release_tag_object=""
release_tag_object=""
expected_release_commit=""
from_release_manifest=""
predecessor_build_info_sha256=""
closure_pre_hop_absent=0
same_version=0
bootstrap_driver=""
bootstrap_driver_ref=""
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
        --bootstrap-driver) [ "$#" -ge 2 ] && [ -z "$bootstrap_driver" ] || die "--bootstrap-driver needs one path"; bootstrap_driver="$2"; shift 2 ;;
        --bootstrap-driver-ref) [ "$#" -ge 2 ] && [ -z "$bootstrap_driver_ref" ] || die "--bootstrap-driver-ref needs one SHA"; bootstrap_driver_ref="$2"; shift 2 ;;
        --release-tag) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$release_tag" ] || die "--release-tag needs one nonempty tag"; release_tag="$2"; shift 2 ;;
        --from-release-tag) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$from_release_tag" ] || die "--from-release-tag needs one nonempty tag"; from_release_tag="$2"; shift 2 ;;
        --from-release-tag-object) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$from_release_tag_object" ] || die "--from-release-tag-object needs one value"; from_release_tag_object="$2"; shift 2 ;;
        --release-tag-object) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$release_tag_object" ] || die "--release-tag-object needs one value"; release_tag_object="$2"; shift 2 ;;
        --from-release-manifest) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$from_release_manifest" ] || die "--from-release-manifest needs one file"; from_release_manifest="$2"; shift 2 ;;
        --predecessor-build-info-sha256) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$predecessor_build_info_sha256" ] || die "--predecessor-build-info-sha256 needs one value"; predecessor_build_info_sha256="$2"; shift 2 ;;
        --expected-release-commit) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$expected_release_commit" ] || die "--expected-release-commit needs one value"; expected_release_commit="$2"; shift 2 ;;
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
[[ "$from" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[1-9][0-9]*)?$ ]] || die "--from must be X.Y.Z"
[[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[1-9][0-9]*)?$ ]] || die "--target must be X.Y.Z"
if [ -n "$release_tag" ] && [ "$release_tag" != "v$target" ]; then
    rc_number="${release_tag#"v$target-rc"}"
    [ "$rc_number" != "$release_tag" ] && [[ "$rc_number" =~ ^[1-9][0-9]*$ ]] \
        || die "--release-tag must be the exact target stable or numbered RC tag"
fi
if [ "$from" = "$target" ]; then
    [ "$release_tag" = "v$target" ] && [ -n "$from_release_tag" ] \
        || die "a same-version hop requires --release-tag v$target and --from-release-tag v$target-rcN"
    from_rc="${from_release_tag#"v$target-rc"}"
    [ "$from_rc" != "$from_release_tag" ] && [[ "$from_rc" =~ ^[1-9][0-9]*$ ]] \
        || die "--from-release-tag must name the installed RC as v$target-rcN"
    [[ "$expected_release_commit" =~ ^[0-9a-f]{40}$ ]] \
        || die "same-version finalization requires --expected-release-commit"
    [ -z "$bootstrap_driver$bootstrap_driver_ref" ] \
        || die "same-version finalization uses the installed release CLI; omit the bootstrap driver"
    [[ "$from_release_tag_object" =~ ^[0-9a-f]{40}$ ]] \
        || die "--from-release-tag-object must be a full lowercase SHA"
    [[ "$release_tag_object" =~ ^[0-9a-f]{40}$ ]] \
        || die "--release-tag-object must be a full lowercase SHA"
    same_version=1
else
    [ -z "$from_release_tag$from_release_tag_object$expected_release_commit$release_tag_object$from_release_manifest$predecessor_build_info_sha256" ] \
        || die "--from-release-tag is only valid when --from equals --target"
fi
if [ -n "$bootstrap_driver$bootstrap_driver_ref" ]; then
    [[ "$bootstrap_driver" =~ ^/[A-Za-z0-9_./-]+$ ]] \
        && [[ "$bootstrap_driver_ref" =~ ^[0-9a-f]{40}$ ]] \
        && [ -n "$release_tag" ] \
        || die "bootstrap requires an absolute literal driver path, full source SHA and explicit release tag"
fi
for named_ref in "$from_pleb_ref" "$from_kilix_ref"; do
    [[ "$named_ref" =~ ^[0-9a-f]{40}$ ]] || die "starting Pleb and Kilix refs must be full lowercase commit SHAs"
done
if [ "$same_version" = 1 ]; then
    [ -f "$from_release_manifest" ] && [ ! -L "$from_release_manifest" ] \
        || die "same-version finalization requires --from-release-manifest"
fi
if [ "$shape" = image ]; then
    [[ "$from_os_ref" =~ ^[0-9a-f]{40}$ ]] || die "image shape requires --from-os-ref as a full lowercase commit SHA"
    [[ "$from_kilix95_ref" =~ ^[0-9a-f]{40}$ ]] || die "image shape requires --from-kilix95-ref as a full lowercase commit SHA"
    [[ "$expected_build_info_sha256" =~ ^[0-9a-f]{64}$ ]] \
        || die "image shape requires --expected-build-info-sha256"
    if [ "$same_version" = 1 ]; then
        [[ "$predecessor_build_info_sha256" =~ ^[0-9a-f]{64}$ ]] \
            || die "same-version image finalization requires --predecessor-build-info-sha256"
    fi
else
    [ -z "$from_os_ref$from_kilix95_ref$expected_build_info_sha256$predecessor_build_info_sha256" ] \
        || die "standalone shape does not accept image-only starting-fixture options"
fi
if [ "$same_version" = 1 ] && [ "$shape" = image ] \
    && [ "$from_os_ref" != "$expected_release_commit" ]; then
    die "--from-os-ref and --expected-release-commit disagree"
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
    release_state="${values[4]}/release-hop/active"
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

# Print one closure value. Returns 2 when the key is absent and 1 when the
# file or the key is malformed.
closure_key() {
    local file="$1" key="$2" count value
    [ -f "$file" ] && [ ! -L "$file" ] || return 1
    count="$(awk -F= -v wanted="$key" '$1 == wanted { count++ } END { print count + 0 }' "$file")"
    if [ "$count" -eq 0 ]; then
        return 2
    fi
    [ "$count" -eq 1 ] || return 1
    value="$(awk -F= -v wanted="$key" '$1 == wanted { sub(/^[^=]*=/, ""); print }' "$file")"
    printf '%s\n' "$value"
}

# Shell assignment values, including leading whitespace, export, and +=.
# Returns 2 when the key is absent and 1 when the file is malformed.
# A textual awk read that disagrees with this value is not the installed value.
closure_shell_value() {
    local file="$1" key="$2"
    [ -f "$file" ] && [ ! -L "$file" ] || return 1
    python3 - "$file" "$key" <<'PY'
import re
import sys
from pathlib import Path

path, key = sys.argv[1], sys.argv[2]
text = Path(path).read_bytes()
if b"\0" in text:
    sys.stderr.write("closure is not text\n")
    raise SystemExit(1)
values = {}
for line_no, raw in enumerate(text.decode().splitlines(), 1):
    line = raw.strip()
    if line == "" or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[len("export "):].strip()
    if "$(" in line or "`" in line:
        sys.stderr.write("closure line %s is not a plain assignment\n" % line_no)
        raise SystemExit(1)
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?=)(.*)$", line)
    if not match:
        sys.stderr.write("malformed closure line %s\n" % line_no)
        raise SystemExit(1)
    name, op, value = match.group(1), match.group(2), match.group(3)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if op == "+=":
        values[name] = values.get(name, "") + value
    else:
        values[name] = value
if key not in values:
    raise SystemExit(2)
sys.stdout.write(values[key] + "\n")
PY
}

# pleb update --show prints "  KEY=value  [source]".
show_resolved_value() {
    local file="$1" key="$2"
    [ -f "$file" ] && [ ! -L "$file" ] || return 1
    python3 - "$file" "$key" <<'PY'
import re
import sys
from pathlib import Path

path, key = sys.argv[1], sys.argv[2]
found = None
for line in Path(path).read_text().splitlines():
    match = re.match(r"^  ([A-Za-z0-9_]+)=(.*?)  \[[^]]*\]\s*$", line)
    if match and match.group(1) == key:
        if found is not None:
            sys.stderr.write("show lists %s more than once\n" % key)
            raise SystemExit(1)
        found = match.group(2)
if found is None:
    raise SystemExit(2)
sys.stdout.write(found + "\n")
PY
}

# Load one key the way the shell would, and refuse an awk read that disagrees.
load_closure_identity() {
    local file="$1" key="$2"
    local shell_rc=0 text_rc=0 shell_value="" text_value=""
    shell_value="$(closure_shell_value "$file" "$key")" || shell_rc=$?
    text_value="$(closure_key "$file" "$key")" || text_rc=$?
    if [ "$shell_rc" -eq 1 ] || [ "$text_rc" -eq 1 ]; then
        return 1
    fi
    if [ "$text_rc" -eq 0 ] && [ "$shell_rc" -eq 0 ] && [ "$text_value" != "$shell_value" ]; then
        printf '%s\n' "closure text and shell disagree on $key" >&2
        return 1
    fi
    if [ "$shell_rc" -eq 2 ]; then
        return 2
    fi
    printf '%s\n' "$shell_value"
}

# RC9 writes selection_tag= into root-only recovery meta. Read a record the
# runner can see directly. Read a root 0700 record with sudo -n. Absent meta
# is not a failure. A recorded tag must equal the published object. A record
# that still cannot be read prints unreadable.
assert_recorded_selection_tag() {
    local root="$1" expected="$2" record meta tag found=0 unreadable=0 body=""
    [ -d "$root" ] && [ ! -L "$root" ] || {
        printf 'absent\n'
        return 0
    }
    if [ ! -r "$root" ] || [ ! -x "$root" ]; then
        printf 'unreadable\n'
        return 0
    fi
    for record in "$root"/closure-rollback.*; do
        [ -d "$record" ] && [ ! -L "$record" ] || continue
        meta="$record/meta"
        body=""
        if [ -r "$record" ] && [ -x "$record" ] && [ ! -L "$meta" ] \
            && [ -f "$meta" ] && [ -r "$meta" ]; then
            body="$(cat -- "$meta")" || { unreadable=1; continue; }
        elif [ -r "$record" ] && [ -x "$record" ] \
            && { [ -L "$meta" ] || [ ! -e "$meta" ]; }; then
            continue
        elif sudo -n test -f "$meta" 2>/dev/null \
            && sudo -n test ! -L "$meta" 2>/dev/null; then
            body="$(sudo -n cat -- "$meta" 2>/dev/null)" || { unreadable=1; continue; }
        elif sudo -n test -L "$meta" 2>/dev/null; then
            continue
        elif sudo -n test -d "$record" 2>/dev/null \
            && sudo -n test ! -e "$meta" 2>/dev/null; then
            continue
        else
            unreadable=1
            continue
        fi
        printf '%s\n' "$body" | grep -q '^selection_tag=' || continue
        tag="$(printf '%s\n' "$body" | sed -n 's/^selection_tag=\([0-9a-f]\{40\}\)$/\1/p')"
        if [ "$tag" != "$expected" ]; then
            printf '%s\n' "recovery meta selection_tag does not match the published RC tag object: $meta" >&2
            return 1
        fi
        found=1
    done
    if [ "$unreadable" -eq 1 ]; then
        printf 'unreadable\n'
        return 0
    fi
    if [ "$found" -eq 1 ]; then
        printf 'matched\n'
    else
        printf 'absent\n'
    fi
}

# matched and absent pass. unreadable is recorded and is not a pass.
record_selection_tag_check() {
    local state="$1"
    if [ "$state" = unreadable ]; then
        record_check "recovery-meta-selection-tag-matches-published-rc-object" not-verified unreadable
        return 0
    fi
    must "recovery-meta-selection-tag-matches-published-rc-object" "$state" \
        test "$state" = matched -o "$state" = absent
}

# An image installed from the RC ISO has build-info and no closure.env.
assert_fresh_iso_identity() {
    local build_info="$1" from_tag="$2" expected_commit="$3" expected_object="$4"
    local ref="" commit="" object="" object_rc=0
    ref="$(closure_shell_value "$build_info" PLEBIAN_OS_REF)" || {
        printf '%s\n' "source build-info has no PLEBIAN_OS_REF" >&2
        return 1
    }
    commit="$(closure_shell_value "$build_info" PLEBIAN_OS_COMMIT)" || {
        printf '%s\n' "source build-info has no PLEBIAN_OS_COMMIT" >&2
        return 1
    }
    if [ "$ref" != "$from_tag" ]; then
        printf '%s\n' "source build-info ref is $ref, expected $from_tag" >&2
        return 1
    fi
    if [ "$commit" != "$expected_commit" ]; then
        printf '%s\n' "source build-info commit is $commit, expected $expected_commit" >&2
        return 1
    fi
    object="$(closure_shell_value "$build_info" PLEBIAN_OS_RELEASE_TAG_OBJECT)" || object_rc=$?
    if [ "$object_rc" -eq 0 ] && [ "$object" != "$expected_object" ]; then
        printf '%s\n' "source build-info tag object is $object, expected $expected_object" >&2
        return 1
    fi
    if [ "$object_rc" -eq 1 ]; then
        return 1
    fi
}

# Release-controlled keys other than PLEBIAN_OS_REF. The manifest's
# PLEBIAN_OS_REF is the RC tag; a selected closure stores the peeled commit.
release_manifest_keys() {
    printf '%s\n' \
        PLEB_REF KILIX_REF KILIX95_REF \
        NEURONTE_REF NEURONTE_REPO \
        PLEBIAN_OS_KILIX_GO_MIN_VERSION PLEBIAN_OS_KILIX_GO_VERSION \
        PLEBIAN_OS_KILIX_GO_DEBIAN_VERSION \
        PLEBIAN_OS_KILIX_GO_SHA256_AMD64 PLEBIAN_OS_KILIX_GO_SHA256_ARM64 \
        PLEBIAN_OS_KILIX_GO_DEB_AMD64_FILE PLEBIAN_OS_KILIX_GO_DEB_AMD64_BYTES \
        PLEBIAN_OS_KILIX_GO_DEB_AMD64_SHA256 \
        PLEBIAN_OS_KILIX_GO_DEB_SRC_FILE PLEBIAN_OS_KILIX_GO_DEB_SRC_BYTES \
        PLEBIAN_OS_KILIX_GO_DEB_SRC_SHA256 \
        PLEBIAN_OS_KILIX_GO_DEB_SNAPSHOT PLEBIAN_OS_KILIX_GO_DEB_MIRROR_URL \
        KILIX_SYSTEM_MONITOR_REF KILIX_DESKTOP_SDK_REF KILIX_ICEWM_REF \
        KILIX_MEDIA_SDK_REF KILIX_WAYDROID_REF KILIX_SECRETS_REF
}

# Closure (or fresh build-info), show-before, and the published RC manifest
# must agree. A key the manifest omits may also be omitted from the closure.
assert_pre_hop_manifest() {
    local closure="$1" show="$2" manifest="$3" from_tag="$4" expected_commit="$5"
    local key ref="" show_ref="" manifest_ref="" commit=""
    local installed="" shown="" published="" installed_rc=0 shown_rc=0 published_rc=0
    ref="$(closure_shell_value "$closure" PLEBIAN_OS_REF)" || {
        printf '%s\n' "installed record has no PLEBIAN_OS_REF" >&2
        return 1
    }
    show_ref="$(show_resolved_value "$show" PLEBIAN_OS_REF)" || {
        printf '%s\n' "show-before has no PLEBIAN_OS_REF" >&2
        return 1
    }
    manifest_ref="$(closure_shell_value "$manifest" PLEBIAN_OS_REF)" || {
        printf '%s\n' "published manifest has no PLEBIAN_OS_REF" >&2
        return 1
    }
    # A fresh ISO's build-info stores the tag. Release-mode session.env stores
    # the commit, and show resolves that. Peel the tag through PLEBIAN_OS_COMMIT.
    if [ "$ref" = "$from_tag" ]; then
        commit="$(closure_shell_value "$closure" PLEBIAN_OS_COMMIT)" || {
            printf '%s\n' "tag-named install record has no PLEBIAN_OS_COMMIT" >&2
            return 1
        }
        if [ "$commit" != "$expected_commit" ]; then
            printf '%s\n' "install record commit is $commit, expected $expected_commit" >&2
            return 1
        fi
        ref="$commit"
    fi
    if [ "$show_ref" != "$ref" ]; then
        printf '%s\n' "show-before PLEBIAN_OS_REF is $show_ref, installed record is $ref" >&2
        return 1
    fi
    if [ "$manifest_ref" != "$from_tag" ]; then
        printf '%s\n' "published manifest PLEBIAN_OS_REF is $manifest_ref, expected $from_tag" >&2
        return 1
    fi
    if [ "$ref" = "$expected_commit" ]; then
        :
    elif [ "$ref" = "$from_tag" ]; then
        commit="$(closure_shell_value "$closure" PLEBIAN_OS_COMMIT)" || {
            printf '%s\n' "tag-named install record has no PLEBIAN_OS_COMMIT" >&2
            return 1
        }
        if [ "$commit" != "$expected_commit" ]; then
            printf '%s\n' "install record commit is $commit, expected $expected_commit" >&2
            return 1
        fi
    else
        printf '%s\n' "installed PLEBIAN_OS_REF is $ref, expected $expected_commit or $from_tag" >&2
        return 1
    fi
    while IFS= read -r key; do
        [ -n "$key" ] || continue
        installed_rc=0
        shown_rc=0
        published_rc=0
        installed="$(closure_shell_value "$closure" "$key")" || installed_rc=$?
        shown="$(show_resolved_value "$show" "$key")" || shown_rc=$?
        published="$(closure_shell_value "$manifest" "$key")" || published_rc=$?
        if [ "$installed_rc" -eq 1 ] || [ "$shown_rc" -eq 1 ] || [ "$published_rc" -eq 1 ]; then
            printf '%s\n' "could not read $key" >&2
            return 1
        fi
        if [ "$published_rc" -eq 2 ] && [ "$installed_rc" -eq 2 ]; then
            continue
        fi
        if [ "$published_rc" -ne 0 ] || [ "$installed_rc" -ne 0 ] || [ "$shown_rc" -ne 0 ] \
            || [ "$installed" != "$published" ] || [ "$shown" != "$published" ]; then
            printf '%s\n' "release key $key does not match the published RC manifest" >&2
            return 1
        fi
    done < <(release_manifest_keys)
}

# Before a same-version hop, the installed closure must name --from-release-tag.
# A recorded closure matches that tag and the published tag object. RC9's
# selector wrote neither key, so the installed PLEBIAN_OS_REF commit is that
# tag's identity. Values are the ones the shell would source.
assert_pre_hop_release_identity() {
    local closure="$1" from_tag="$2" expected_commit="$3" expected_object="${4:-}"
    local tag="" object="" ref="" tag_rc=0 object_rc=0 ref_rc=0
    [[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || {
            printf '%s\n' "expected release commit is not a full SHA" >&2
            return 1
        }
    tag="$(load_closure_identity "$closure" PLEBIAN_OS_RELEASE_TAG)" || tag_rc=$?
    object="$(load_closure_identity "$closure" PLEBIAN_OS_RELEASE_TAG_OBJECT)" || object_rc=$?
    ref="$(load_closure_identity "$closure" PLEBIAN_OS_REF)" || ref_rc=$?
    if [ "$tag_rc" -ne 0 ] && [ "$tag_rc" -ne 2 ]; then
        printf '%s\n' "installed PLEBIAN_OS_RELEASE_TAG is malformed" >&2
        return 1
    fi
    if [ "$object_rc" -ne 0 ] && [ "$object_rc" -ne 2 ]; then
        printf '%s\n' "installed PLEBIAN_OS_RELEASE_TAG_OBJECT is malformed" >&2
        return 1
    fi
    if [ "$ref_rc" -eq 1 ]; then
        printf '%s\n' "installed PLEBIAN_OS_REF is malformed" >&2
        return 1
    fi
    if [ "$tag_rc" -eq 0 ]; then
        if [ "$tag" != "$from_tag" ]; then
            printf '%s\n' "installed release tag is $tag, expected $from_tag" >&2
            return 1
        fi
        if [[ ! "$object" =~ ^[0-9a-f]{40}$ ]]; then
            printf '%s\n' "installed release tag has no tag object" >&2
            return 1
        fi
        if [ -z "$expected_object" ]; then
            printf '%s\n' "installed tag object cannot be checked without the published object" >&2
            return 1
        fi
        if [ -n "$expected_object" ] && [ "$object" != "$expected_object" ]; then
            printf '%s\n' "installed tag object is $object, expected $expected_object" >&2
            return 1
        fi
    elif [ "$object_rc" -eq 0 ]; then
        if [ -z "$expected_object" ]; then
            printf '%s\n' "installed tag object cannot be checked without the published object" >&2
            return 1
        fi
        if [ "$object" != "$expected_object" ]; then
            printf '%s\n' "installed tag object is $object, expected $expected_object" >&2
            return 1
        fi
    else
        if [ "$ref_rc" -ne 0 ]; then
            printf '%s\n' "unrecorded closure has no PLEBIAN_OS_REF" >&2
            return 1
        fi
        if [ "$ref" != "$expected_commit" ]; then
            printf '%s\n' "unrecorded closure commit is $ref, expected $expected_commit" >&2
            return 1
        fi
    fi
    if [ "$ref_rc" -eq 0 ] && [ "$ref" != "$expected_commit" ]; then
        printf '%s\n' "installed PLEBIAN_OS_REF is $ref, expected $expected_commit" >&2
        return 1
    fi
}

# After the hop, the closure tag is the stable final and its object is the
# object staged in the release-hop active record (line 3; the tag is line 5).
assert_post_hop_release_identity() {
    local closure="$1" active="$2" target_tag="$3"
    local tag="" object="" staged_object="" staged_tag="" tag_rc=0 object_rc=0
    tag="$(closure_key "$closure" PLEBIAN_OS_RELEASE_TAG)" || tag_rc=$?
    object="$(closure_key "$closure" PLEBIAN_OS_RELEASE_TAG_OBJECT)" || object_rc=$?
    if [ "$tag_rc" -ne 0 ] || [ "$object_rc" -ne 0 ]; then
        printf '%s\n' "selected closure does not record a release tag and tag object" >&2
        return 1
    fi
    if [ "$tag" != "$target_tag" ]; then
        printf '%s\n' "selected release tag is $tag, expected $target_tag" >&2
        return 1
    fi
    if [[ ! "$object" =~ ^[0-9a-f]{40}$ ]]; then
        printf '%s\n' "selected tag object is not a full SHA" >&2
        return 1
    fi
    if [ ! -f "$active" ] || [ -L "$active" ]; then
        printf '%s\n' "staged release-hop state is missing" >&2
        return 1
    fi
    staged_object="$(sed -n '3p' "$active")"
    staged_tag="$(sed -n '5p' "$active")"
    if [ "$staged_tag" != "$target_tag" ]; then
        printf '%s\n' "staged release tag is $staged_tag, expected $target_tag" >&2
        return 1
    fi
    if [ "$object" != "$staged_object" ]; then
        printf '%s\n' "tag-object mismatch: closure $object, staged $staged_object" >&2
        return 1
    fi
    if [ -n "${4:-}" ] && [ "$object" != "$4" ]; then
        printf '%s\n' "selected tag object is $object, expected published $4" >&2
        return 1
    fi
}

# installed, source-iso hash, published predecessor hash.
# Prints source-iso or installed-closure. Anything else fails.
classify_installed_build_info() {
    local installed="$1" source="$2" predecessor="${3:-}"
    if [ "$installed" = "$source" ]; then
        printf '%s\n' source-iso
        return 0
    fi
    if [ -n "$predecessor" ] && [ "$installed" = "$predecessor" ]; then
        printf '%s\n' installed-closure
        return 0
    fi
    printf '%s\n' "installed build-info $installed is neither the source ISO nor the published predecessor" >&2
    return 1
}

# Manifest lines are "fingerprint<TAB>path<TAB>expected" or "head<TAB>path<TAB>sha".
# A difference prints "<label> did not restore <path>".
assert_release_snapshot_restored() {
    local label="$1" manifest="$2"
    local kind path expected actual failed=0
    [ -f "$manifest" ] || return 1
    while IFS=$'\t' read -r kind path expected || [ -n "${kind:-}" ]; do
        [ -n "$kind" ] || continue
        case "$kind" in
            fingerprint) actual="$(path_fingerprint "$path")" ;;
            head)
                [ -d "$path/.git" ] || actual="missing"
                if [ -d "$path/.git" ]; then
                    actual="$(git -C "$path" rev-parse --verify 'HEAD^{commit}')" || return 1
                fi
                ;;
            engine)
                actual="$(bound_engine_fingerprint | sha256sum | awk '{print $1}')" || return 1
                ;;
            *) printf '%s\n' "$label did not restore $path" >&2; return 1 ;;
        esac
        if [ "$actual" != "$expected" ]; then
            printf '%s\n' "$label did not restore $path" >&2
            failed=1
        fi
    done <"$manifest"
    [ "$failed" -eq 0 ]
}

# Pleb keeps one generation of rollback. release-hop/active names the hop that
# --rollback would undo: a new hop replaces an earlier completed record when it
# starts, and a successful rollback consumes the record it used, so the record
# a guest carried before the hop (left by an earlier completed hop) cannot come
# back. What a rolled-back machine must show is no record, phase or baseline at
# all; every other path must be what it was. Comparing the pre-hop fingerprint
# of the record would fail every guest that has hop history.
rollback_expected_manifest() {
    local source="$1" target="$2" state_dir
    state_dir="$(dirname -- "$release_state")"
    awk -F '\t' -v OFS='\t' -v state="$release_state" \
        '$1 == "fingerprint" && $2 == state { $3 = "absent" } { print }' \
        "$source" >"$target" || return 1
    printf 'fingerprint\t%s\t%s\n' "$state_dir/phase" absent \
        "$state_dir/baseline" absent "$state_dir/unselected-checkouts" absent >>"$target"
}

record_release_snapshot() {
    local manifest="$1" path
    : >"$manifest"
    for path in "$session_env" "$closure_env" "$settings_file" \
        /usr/local/bin/plebian-os-select-closure /usr/local/bin/plebian-os-update; do
        printf 'fingerprint\t%s\t%s\n' "$path" "$(path_fingerprint "$path")" >>"$manifest"
    done
    printf 'fingerprint\t%s\t%s\n' "$release_state" \
        "$(path_fingerprint "$release_state")" >>"$manifest"
    printf 'engine\t%s\t%s\n' "$engine_build" \
        "$(bound_engine_fingerprint | sha256sum | awk '{print $1}')" >>"$manifest"
    if [ "$shape" = image ]; then
        printf 'head\t%s\t%s\n' "$os_dir" \
            "$(git -C "$os_dir" rev-parse --verify 'HEAD^{commit}')" >>"$manifest"
        printf 'head\t%s\t%s\n' "$kilix95_dir" \
            "$(git -C "$kilix95_dir" rev-parse --verify 'HEAD^{commit}')" >>"$manifest"
    fi
    printf 'head\t%s\t%s\n' "$pleb_dir" \
        "$(git -C "$pleb_dir" rev-parse --verify 'HEAD^{commit}')" >>"$manifest"
    printf 'head\t%s\t%s\n' "$kilix_dir" \
        "$(git -C "$kilix_dir" rev-parse --verify 'HEAD^{commit}')" >>"$manifest"
}

# Every closure key, including the release tag object, byte for byte.
closure_keys_match() {
    python3 - "$1" "$2" <<'PY'
import sys
from pathlib import Path

def load(path):
    found = {}
    text = Path(path).read_bytes()
    if b"\0" in text:
        raise SystemExit("closure is not text")
    for line_no, line in enumerate(text.decode().splitlines(), 1):
        if line == "" or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit("malformed closure line %s" % line_no)
        name, value = line.split("=", 1)
        if name == "" or name in found:
            raise SystemExit("duplicate or empty closure key on line %s" % line_no)
        found[name] = value
    return found

before = load(sys.argv[1])
after = load(sys.argv[2])
if before != after:
    only_before = sorted(set(before) - set(after))
    only_after = sorted(set(after) - set(before))
    changed = sorted(key for key in set(before) & set(after) if before[key] != after[key])
    detail = []
    if only_before:
        detail.append("missing " + ",".join(only_before))
    if only_after:
        detail.append("unexpected " + ",".join(only_after))
    if changed:
        detail.append("changed " + ",".join(changed))
    sys.stderr.write("closure mismatch: " + "; ".join(detail) + "\n")
    raise SystemExit(1)
PY
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
        if [ -n "${release_tag:-}" ]; then
            printf 'test "$(sed -n 5p %q)" = %q\n' "$release_state" "$release_tag"
            if [ "${same_version:-0}" = 1 ]; then
                printf 'test "$(sed -n 3p %q)" = %q\n' "$release_state" \
                    "$(sed -n '3p' "$release_state")"
            fi
            printf 'test "$(sha256sum -- %q | cut -d " " -f 1)" = %q\n' \
                "$release_state" "$(sha256sum -- "$release_state" | cut -d ' ' -f 1)"
        fi
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
    if [ "$same_version" = 1 ] && [ "$installed_build_info_sha256" != "$expected_build_info_sha256" ]; then
        # An upgrade to the RC leaves the predecessor ISO's build-info in place.
        # That hash must be the published predecessor listed in its SHA256SUMS.
        build_info_binding="$(classify_installed_build_info \
            "$installed_build_info_sha256" "$expected_build_info_sha256" \
            "$predecessor_build_info_sha256")" || build_info_binding=""
        must "image-build-info-is-install-predecessor" \
            "installed $installed_build_info_sha256; predecessor $predecessor_build_info_sha256; source ISO $expected_build_info_sha256" \
            test "$build_info_binding" = installed-closure
    else
        must "image-build-info-matches-published-fixture" \
            "$installed_build_info_sha256/$expected_build_info_sha256" \
            test "$installed_build_info_sha256" = "$expected_build_info_sha256"
    fi
    must "image-os-checkout-exists" "$os_dir" test -d "$os_dir/.git"
    must "image-kilix95-checkout-exists" "$kilix95_dir" test -d "$kilix95_dir/.git"
    os_start_head="$(git -C "$os_dir" rev-parse --verify 'HEAD^{commit}')"
    kilix95_start_head="$(git -C "$kilix95_dir" rev-parse --verify 'HEAD^{commit}')"
    must "starting-os-ref-is-exact" "$os_start_head/$from_os_ref" \
        test "$os_start_head" = "$from_os_ref"
    must "starting-kilix95-ref-is-exact" "$kilix95_start_head/$from_kilix95_ref" \
        test "$kilix95_start_head" = "$from_kilix95_ref"
fi

hop_command=("$pleb_bin")
hop_entrypoint_mode="installed-cli"
if [ -n "$bootstrap_driver" ]; then
    [ -x "$bootstrap_driver" ] || die "bootstrap driver is not executable"
    hop_command=("$bootstrap_driver" --installed-pleb "$pleb_bin" --driver-ref "$bootstrap_driver_ref" --)
    hop_entrypoint_mode=explicit-legacy-bootstrap
    printf '%s\n' "$bootstrap_driver_ref" >"$report/bootstrap-driver.ref"
fi
release_args=()
[ -z "$release_tag" ] || release_args=(--release-tag "$release_tag")
"${hop_command[@]}" update --help >"$report/pleb-update-help.txt" 2>&1
if [ -n "${release_tag:-}" ]; then
    must "selected-entrypoint-supports-explicit-tag" "$hop_entrypoint_mode --release-tag" \
        grep -q -- '--release-tag' "$report/pleb-update-help.txt"
fi
must "selected-entrypoint-supports-named-hop" "$hop_entrypoint_mode --to" \
    grep -q -- '--to X.Y.Z' "$report/pleb-update-help.txt"
"$pleb_bin" update --show >"$report/show-before.txt" 2>"$report/show-before.stderr"
current="$(sed -n 's/^  PLEBIAN_OS_VERSION=\([^ ]*\).*/\1/p' "$report/show-before.txt" | head -n 1)"
[[ "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[1-9][0-9]*)?$ ]] \
    || die "could not resolve the installed release from pleb update --show"
must "starting-release-is-exact" "$current/$from" test "$current" = "$from"
if [ "$same_version" = 1 ]; then
    if [ -f "$closure_env" ] && [ ! -L "$closure_env" ]; then
        must "installed-release-identity-is-from-release-tag" "$from_release_tag" \
            assert_pre_hop_release_identity "$closure_env" "$from_release_tag" \
            "$expected_release_commit" "$from_release_tag_object"
        cp -p -- "$closure_env" "$report/closure.pre-hop"
        closure_pre_hop_absent=0
        must "installed-closure-matches-published-rc-manifest" "$from_release_manifest" \
            assert_pre_hop_manifest "$closure_env" "$report/show-before.txt" \
            "$from_release_manifest" "$from_release_tag" "$expected_release_commit"
    elif [ "$shape" = image ] \
        && [ "$installed_build_info_sha256" = "$expected_build_info_sha256" ]; then
        must "installed-release-identity-is-source-build-info" "$from_release_tag" \
            assert_fresh_iso_identity /etc/plebian-os/build-info.env \
            "$from_release_tag" "$expected_release_commit" "$from_release_tag_object"
        closure_pre_hop_absent=1
        must "installed-build-info-matches-published-rc-manifest" "$from_release_manifest" \
            assert_pre_hop_manifest /etc/plebian-os/build-info.env "$report/show-before.txt" \
            "$from_release_manifest" "$from_release_tag" "$expected_release_commit"
    else
        die "same-version finalization requires the installed closure, or an image build-info that matches the source ISO"
    fi
    if [ "$shape" = image ]; then
        selection_tag_state="$(assert_recorded_selection_tag /var/lib/plebian-os "$from_release_tag_object")" \
            || die "installed recovery meta selection_tag does not match --from-release-tag-object"
        record_selection_tag_check "$selection_tag_state"
    fi
else
    must "target-differs-from-installed-release" "$current -> $target" test "$current" != "$target"
fi

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
"${hop_command[@]}" update --to "$target" "${release_args[@]}" --dry-run --yes --no-restart \
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
    "${hop_command[@]}" update --to "$target" "${release_args[@]}" --yes --no-restart \
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

if [ "$same_version" = 1 ]; then
    record_release_snapshot "$report/release-snapshot.pre-hop"
fi

failure_boundary=closure
set +e
PLEBIAN_OS_SELECT_TEST_FAIL_AFTER="$failure_boundary" \
    "${hop_command[@]}" update --to "$target" "${release_args[@]}" --yes --no-restart \
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
if [ "$same_version" = 1 ] && [ "$closure_pre_hop_absent" != 1 ]; then
    must "failure-restores-closure-keys" "$closure_env" \
        closure_keys_match "$report/closure.pre-hop" "$closure_env"
fi
must "failure-restores-settings" "$settings_file" \
    test "$(path_fingerprint "$settings_file")" = "$settings_before"
must "failure-restores-engine-generation" "$engine_build" \
    test "$(bound_engine_fingerprint)" = "$engine_before"
home_manifest "$report/home-after-failure.tsv"
diff -u "$report/home-before-failure.tsv" "$report/home-after-failure.tsv" \
    >"$report/home-induced-failure.diff" || true

set +e
"${hop_command[@]}" update --to "$target" "${release_args[@]}" --yes --no-restart \
    >"$report/success.stdout" 2>"$report/success.stderr"
success_rc=$?
set -e
printf '%s\n' "$success_rc" >"$report/success.exit"
must "single-command-hop-succeeds" "pleb update --to $target; exit=$success_rc" test "$success_rc" -eq 0
"$pleb_bin" update --show >"$report/show-after.txt" 2>"$report/show-after.stderr"
selected="$(sed -n 's/^  PLEBIAN_OS_VERSION=\([^ ]*\).*/\1/p' "$report/show-after.txt" | head -n 1)"
must "selected-release-is-target" "$selected/$target" test "$selected" = "$target"
if [ -n "${release_tag:-}" ]; then
    must "selected-release-tag-is-exact" "$release_tag" \
        test "$(sed -n '5p' "$release_state")" = "$release_tag"
    cp -- "$release_state" "$report/release-hop-active.after"
fi
rollback_commands=0
restoring_hops=0
if [ "$same_version" = 1 ]; then
    must "selected-release-tag-object-is-staged" "$release_tag" \
        assert_post_hop_release_identity "$closure_env" "$release_state" "$release_tag" \
        "$release_tag_object"
    cp -p -- "$closure_env" "$report/closure.post-hop"
    record_release_snapshot "$report/release-snapshot.post-hop"
    set +e
    "$pleb_bin" update --rollback --yes --no-restart \
        >"$report/rollback.stdout" 2>"$report/rollback.stderr"
    rollback_rc=$?
    set -e
    printf '%s\n' "$rollback_rc" >"$report/rollback.exit"
    rollback_commands=1
    must "rollback-from-final-succeeds" "pleb update --rollback; exit=$rollback_rc" \
        test "$rollback_rc" -eq 0
    rollback_expected_manifest "$report/release-snapshot.pre-hop" \
        "$report/release-snapshot.rollback-expected"
    must "rollback-restores-pre-hop-state" "session closure settings selector updater and checkout heads; no hop record left" \
        assert_release_snapshot_restored rollback "$report/release-snapshot.rollback-expected"
    closure_env_live="$closure_env"
    if [ "$closure_pre_hop_absent" != 1 ]; then
        must "rollback-restores-rc-closure-keys" "$closure_env" \
            closure_keys_match "$report/closure.pre-hop" "$closure_env"
        must "rollback-restores-rc-closure-bytes" "$closure_env" \
        cmp -s "$report/closure.pre-hop" "$closure_env"
    set +e
    else
        # The closure path is absent. Comparing two harness-written "absent"
        # files cannot fail, so that check is not recorded.
        must "rollback-restores-absent-closure" "$closure_env" test ! -e "$closure_env"
        set +e
    fi
    closure_env="$closure_env_live"
    "${hop_command[@]}" update --to "$target" "${release_args[@]}" --yes --no-restart \
        >"$report/restoring-hop.stdout" 2>"$report/restoring-hop.stderr"
    restoring_rc=$?
    set -e
    printf '%s\n' "$restoring_rc" >"$report/restoring-hop.exit"
    restoring_hops=1
    must "restoring-hop-succeeds" "pleb update --to $target; exit=$restoring_rc" \
        test "$restoring_rc" -eq 0
    "$pleb_bin" update --show >"$report/show-after.txt" 2>"$report/show-after.stderr"
    selected="$(sed -n 's/^  PLEBIAN_OS_VERSION=\([^ ]*\).*/\1/p' "$report/show-after.txt" | head -n 1)"
    must "restoring-hop-release-is-target" "$selected/$target" test "$selected" = "$target"
    must "restoring-hop-tag-is-exact" "$release_tag" \
        test "$(sed -n '5p' "$release_state")" = "$release_tag"
    cp -- "$release_state" "$report/release-hop-active.after"
    must "restoring-hop-tag-object-is-staged" "$release_tag" \
        assert_post_hop_release_identity "$closure_env" "$release_state" "$release_tag" \
        "$release_tag_object"
    must "restoring-hop-restores-post-hop-state" "session closure settings selector updater and checkout heads" \
        assert_release_snapshot_restored "restoring hop" "$report/release-snapshot.post-hop"
fi
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
if [ "$same_version" = 1 ]; then
    record_check "evidence-artifacts-written" pass \
        "home manifests 4/4; failure/success hop logs 2/2; rollback and restoring hop logs 2/2"
else
    record_check "evidence-artifacts-written" pass "home manifests 4/4; failure/success hop logs 2/2"
fi

export F109_REPORT_SHAPE="$shape" F109_REPORT_TARGET="$target"
export F109_REPORT_TAG="$release_tag" F109_REPORT_FROM_TAG="$from_release_tag"
export F109_REPORT_FROM_TAG_OBJECT="$from_release_tag_object"
export F109_REPORT_TAG_OBJECT="$release_tag_object"
export F109_REPORT_DRIVER_REF="$bootstrap_driver_ref" F109_REPORT_ENTRYPOINT="$hop_entrypoint_mode"
export F109_REPORT_ROLLBACK_COMMANDS="${rollback_commands:-0}"
export F109_REPORT_RESTORING_HOPS="${restoring_hops:-0}"
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
        "release_tag": os.environ["F109_REPORT_TAG"] or None,
        "from_release_tag": os.environ["F109_REPORT_FROM_TAG"] or None,
        "from_release_tag_object": os.environ["F109_REPORT_FROM_TAG_OBJECT"] or None,
        "release_tag_object": os.environ["F109_REPORT_TAG_OBJECT"] or None,
        "entrypoint_mode": os.environ["F109_REPORT_ENTRYPOINT"],
        "bootstrap_driver_ref": os.environ["F109_REPORT_DRIVER_REF"] or None,
        "dry_run_commands": 1,
        "dry_run_command_denominator": 1,
        "successful_hop_commands": 1,
        "successful_hop_command_denominator": 1,
        "rollback_from_final_commands": int(os.environ["F109_REPORT_ROLLBACK_COMMANDS"]),
        "restoring_hop_commands": int(os.environ["F109_REPORT_RESTORING_HOPS"]),
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
