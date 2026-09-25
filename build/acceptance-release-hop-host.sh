#!/usr/bin/env bash
# acceptance-release-hop-host.sh — control F109's two real-VM hop lanes.
#
# The guests are prepared separately because the image lane starts from the
# published previous Plebian-OS ISO while the standalone lane starts from a
# plain Debian install. This controller proves the published artifact checksum,
# binds the installed image guest to the ISO's embedded build information,
# requires two distinct VM identities, drives both guest controls, retrieves and
# verifies both evidence sets, reboots successful guests, and verifies the target
# release after reboot.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
GUEST_RUNNER="$HERE/acceptance-release-hop.sh"

usage() {
    cat <<'EOF'
usage: acceptance-release-hop-host.sh --from X.Y.Z --target X.Y.Z \
       --source-iso FILE --source-sha256sums FILE \
       --image-guest USER@HOST [--image-port PORT] \
       --standalone-guest USER@HOST [--standalone-port PORT] \
       --known-hosts FILE [--identity FILE] --report DIR

Both guests must already be disposable VMs reachable with public-key SSH and
non-interactive sudo. The image guest must have been installed from FILE; the
standalone guest must contain the exact Pleb and Kilix refs embedded in FILE.
DIR must be new or empty. A passing run always executes and verifies 2/2 lanes.
EOF
}

die() {
    printf 'acceptance-release-hop-host: %s\n' "$*" >&2
    exit 1
}

from=""
target=""
source_iso=""
source_sha256sums=""
image_guest=""
image_port=22
standalone_guest=""
standalone_port=22
known_hosts=""
identity=""
report=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --from) [ "$#" -ge 2 ] || die "--from needs a value"; from="$2"; shift 2 ;;
        --target) [ "$#" -ge 2 ] || die "--target needs a value"; target="$2"; shift 2 ;;
        --source-iso) [ "$#" -ge 2 ] || die "--source-iso needs a value"; source_iso="$2"; shift 2 ;;
        --source-sha256sums) [ "$#" -ge 2 ] || die "--source-sha256sums needs a value"; source_sha256sums="$2"; shift 2 ;;
        --image-guest) [ "$#" -ge 2 ] || die "--image-guest needs a value"; image_guest="$2"; shift 2 ;;
        --image-port) [ "$#" -ge 2 ] || die "--image-port needs a value"; image_port="$2"; shift 2 ;;
        --standalone-guest) [ "$#" -ge 2 ] || die "--standalone-guest needs a value"; standalone_guest="$2"; shift 2 ;;
        --standalone-port) [ "$#" -ge 2 ] || die "--standalone-port needs a value"; standalone_port="$2"; shift 2 ;;
        --known-hosts) [ "$#" -ge 2 ] || die "--known-hosts needs a value"; known_hosts="$2"; shift 2 ;;
        --identity) [ "$#" -ge 2 ] || die "--identity needs a value"; identity="$2"; shift 2 ;;
        --report) [ "$#" -ge 2 ] || die "--report needs a value"; report="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[[ "$from" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "--from must be X.Y.Z"
[[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "--target must be X.Y.Z"
[ "$from" != "$target" ] || die "--from and --target must differ"
for destination in "$image_guest" "$standalone_guest"; do
    [[ "$destination" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._:-]+$ ]] \
        || die "guest destinations must be literal USER@HOST values"
done
for port in "$image_port" "$standalone_port"; do
    if ! [[ "$port" =~ ^[0-9]+$ ]] \
        || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
        die "guest ports must be integers from 1 through 65535"
    fi
done
[ -n "$source_iso" ] || die "--source-iso is required"
[ -n "$source_sha256sums" ] || die "--source-sha256sums is required"
[ -n "$known_hosts" ] || die "--known-hosts is required"
[ -n "$report" ] || die "--report is required"

for command_name in awk find git python3 realpath seq sha256sum ssh xorriso; do
    command -v "$command_name" >/dev/null 2>&1 || die "$command_name is required"
done
[ -x "$GUEST_RUNNER" ] || die "guest runner is not executable: $GUEST_RUNNER"
[ -f "$source_iso" ] || die "source ISO does not exist: $source_iso"
[ -f "$source_sha256sums" ] || die "source checksum file does not exist: $source_sha256sums"
[ -s "$known_hosts" ] || die "known-hosts file must exist and be nonempty: $known_hosts"
if [ -n "$identity" ]; then
    [ -f "$identity" ] || die "identity file does not exist: $identity"
fi
[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=normal)" ] \
    || die "refusing a dirty Plebian-OS qualification checkout"

source_iso="$(realpath -e -- "$source_iso")"
source_sha256sums="$(realpath -e -- "$source_sha256sums")"
known_hosts="$(realpath -e -- "$known_hosts")"
if [ -n "$identity" ]; then identity="$(realpath -e -- "$identity")"; fi

iso_basename="$(basename -- "$source_iso")"
expected_iso_sha256=""
checksum_matches=0
while IFS= read -r checksum_line || [ -n "$checksum_line" ]; do
    if [[ "$checksum_line" =~ ^([0-9A-Fa-f]{64})[[:space:]]+\*?(.+)$ ]]; then
        checksum_name="${BASH_REMATCH[2]}"
        if [ "$checksum_name" = "$iso_basename" ] || [ "$checksum_name" = "./$iso_basename" ]; then
            expected_iso_sha256="${BASH_REMATCH[1],,}"
            checksum_matches=$((checksum_matches + 1))
        fi
    fi
done <"$source_sha256sums"
[ "$checksum_matches" -eq 1 ] \
    || die "checksum file must name the source ISO exactly once; found $checksum_matches/1"
actual_iso_sha256="$(sha256sum -- "$source_iso" | awk '{print $1}')"
[ "$actual_iso_sha256" = "$expected_iso_sha256" ] \
    || die "source ISO checksum mismatch: $actual_iso_sha256/$expected_iso_sha256"

mkdir -p -- "$report"
report="$(cd "$report" && pwd -P)"
[ -z "$(find "$report" -mindepth 1 -maxdepth 1 -print -quit)" ] \
    || die "report directory must be empty: $report"
chmod 0700 "$report"

source_build_info="$report/source-build-info.env"
xorriso -osirrox on -indev "$source_iso" \
    -extract /plebian-os/build-info.env "$source_build_info" >/dev/null 2>"$report/xorriso.stderr" \
    || die "could not extract the source ISO build information"
source_build_info_sha256="$(sha256sum "$source_build_info" | awk '{print $1}')"

build_info_value() {
    local key="$1" file="$2" count value
    count="$(awk -F= -v wanted="$key" '$1 == wanted { count++ } END { print count + 0 }' "$file")"
    [ "$count" -eq 1 ] || die "$file must contain $key exactly once; found $count/1"
    value="$(awk -F= -v wanted="$key" '$1 == wanted { sub(/^[^=]*=/, ""); print }' "$file")"
    printf '%s\n' "$value"
}

source_version="$(build_info_value PLEBIAN_OS_VERSION "$source_build_info")"
from_os_ref="$(build_info_value PLEBIAN_OS_COMMIT "$source_build_info")"
from_pleb_ref="$(build_info_value PLEB_REF "$source_build_info")"
from_kilix_ref="$(build_info_value KILIX_REF "$source_build_info")"
from_kilix95_ref="$(build_info_value KILIX95_REF "$source_build_info")"
[ "$source_version" = "$from" ] \
    || die "source ISO version is $source_version, expected --from $from"
for fixture_ref in "$from_os_ref" "$from_pleb_ref" "$from_kilix_ref" "$from_kilix95_ref"; do
    [[ "$fixture_ref" =~ ^[0-9a-f]{40}$ ]] \
        || die "source ISO contains a non-commit starting ref: $fixture_ref"
done

ssh_options=(
    -F /dev/null
    -o BatchMode=yes
    -o StrictHostKeyChecking=yes
    -o "UserKnownHostsFile=$known_hosts"
    -o ConnectTimeout=5
    -o ConnectionAttempts=1
    -o ServerAliveInterval=30
    -o ServerAliveCountMax=10
    -o LogLevel=ERROR
)
if [ -n "$identity" ]; then
    ssh_options+=(-o IdentitiesOnly=yes -i "$identity")
fi

remote_exec() {
    local destination="$1" port="$2"
    shift 2
    ssh "${ssh_options[@]}" -p "$port" "$destination" "$@"
}

probe_guest() {
    local destination="$1" port="$2"
    # This is a literal remote program; expansion belongs to the guest shell.
    # shellcheck disable=SC2016
    remote_exec "$destination" "$port" \
        'set -eu; machine=$(cat /etc/machine-id); virt=$(systemd-detect-virt --vm); boot=$(cat /proc/sys/kernel/random/boot_id); sudo -n true; printf "%s\t%s\t%s\n" "$machine" "$virt" "$boot"'
}

image_probe="$(probe_guest "$image_guest" "$image_port")" \
    || die "image guest preflight failed"
standalone_probe="$(probe_guest "$standalone_guest" "$standalone_port")" \
    || die "standalone guest preflight failed"
IFS=$'\t' read -r image_machine_id image_virt image_boot_id <<<"$image_probe"
IFS=$'\t' read -r standalone_machine_id standalone_virt standalone_boot_id <<<"$standalone_probe"
[[ "$image_machine_id" =~ ^[0-9a-f]{32}$ ]] || die "image guest returned an invalid machine-id"
[[ "$standalone_machine_id" =~ ^[0-9a-f]{32}$ ]] || die "standalone guest returned an invalid machine-id"
[ "$image_machine_id" != "$standalone_machine_id" ] \
    || die "image and standalone lanes must use distinct VMs; machine-id matches 1/1"
for virt in "$image_virt" "$standalone_virt"; do
    if [ -z "$virt" ] || [ "$virt" = none ]; then
        die "both guests must report VM virtualization"
    fi
done

installed_build_info_sha256="$(remote_exec "$image_guest" "$image_port" \
    "sha256sum /etc/plebian-os/build-info.env | cut -d' ' -f1")" \
    || die "could not hash the image guest's installed build information"
[ "$installed_build_info_sha256" = "$source_build_info_sha256" ] \
    || die "image guest is not bound to the source ISO build information"

declare -A lane_runner_rc=()
declare -A lane_retrieve_rc=()
declare -A lane_checksum_rc=()
declare -A lane_reboot_rc=()
declare -A lane_post_version=()

extract_lane_archive() {
    local archive="$1" destination="$2"
    python3 - "$archive" "$destination" <<'PY'
import re
import sys
import tarfile
from pathlib import Path

archive = Path(sys.argv[1])
destination = Path(sys.argv[2])
allowed = re.compile(r"[A-Za-z0-9._-]+")
with tarfile.open(archive, "r:*") as bundle:
    members = bundle.getmembers()
    if not members:
        raise SystemExit("empty guest evidence archive")
    for member in members:
        name = member.name.removeprefix("./")
        if name in ("", ".") and member.isdir():
            continue
        if not allowed.fullmatch(name) or not member.isfile():
            raise SystemExit(f"unsafe guest evidence member: {member.name!r}")
        source = bundle.extractfile(member)
        if source is None:
            raise SystemExit(f"unreadable guest evidence member: {member.name!r}")
        target = destination / name
        with target.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
PY
}

run_lane() {
    local shape="$1" destination="$2" port="$3" boot_id="$4"
    local lane_dir="$report/$shape" remote_report="/var/tmp/f109-$shape-hop-${target//./-}"
    local remote_command runner_rc retrieve_rc checksum_rc reboot_rc new_boot_id post_version
    mkdir -p -- "$lane_dir"
    remote_exec "$destination" "$port" "test ! -e $remote_report" \
        >"$lane_dir/remote-report-preflight.stdout" \
        2>"$lane_dir/remote-report-preflight.stderr" \
        || die "$shape guest report path already exists: $remote_report"

    remote_command="bash -s -- --shape $shape --from $from --target $target --from-pleb-ref $from_pleb_ref --from-kilix-ref $from_kilix_ref --report $remote_report --disposable-vm"
    if [ "$shape" = image ]; then
        remote_command+=" --from-os-ref $from_os_ref --from-kilix95-ref $from_kilix95_ref --expected-build-info-sha256 $source_build_info_sha256"
    fi
    set +e
    remote_exec "$destination" "$port" "$remote_command" <"$GUEST_RUNNER" \
        >"$lane_dir/runner.stdout" 2>"$lane_dir/runner.stderr"
    runner_rc=$?
    set -e
    printf '%s\n' "$runner_rc" >"$lane_dir/runner.exit"

    set +e
    remote_exec "$destination" "$port" \
        "test -d $remote_report && tar -C $remote_report -cf - ." \
        >"$lane_dir/guest-evidence.tar" 2>"$lane_dir/retrieve.stderr"
    retrieve_rc=$?
    if [ "$retrieve_rc" -eq 0 ]; then
        extract_lane_archive "$lane_dir/guest-evidence.tar" "$lane_dir" \
            >"$lane_dir/extract.stdout" 2>"$lane_dir/extract.stderr"
        retrieve_rc=$?
    fi
    set -e
    printf '%s\n' "$retrieve_rc" >"$lane_dir/retrieve.exit"

    checksum_rc=1
    if [ "$retrieve_rc" -eq 0 ] && [ -f "$lane_dir/SHA256SUMS" ]; then
        set +e
        (cd "$lane_dir" && sha256sum -c SHA256SUMS) \
            >"$lane_dir/checksum.stdout" 2>"$lane_dir/checksum.stderr"
        checksum_rc=$?
        set -e
    fi
    printf '%s\n' "$checksum_rc" >"$lane_dir/checksum.exit"

    reboot_rc=1
    post_version=""
    if [ "$runner_rc" -eq 0 ] && [ "$retrieve_rc" -eq 0 ] && [ "$checksum_rc" -eq 0 ]; then
        set +e
        remote_exec "$destination" "$port" 'sudo -n systemctl reboot' \
            >"$lane_dir/reboot.stdout" 2>"$lane_dir/reboot.stderr"
        set -e
        new_boot_id=""
        for _attempt in $(seq 1 120); do
            set +e
            new_boot_id="$(remote_exec "$destination" "$port" \
                'cat /proc/sys/kernel/random/boot_id' 2>/dev/null)"
            set -e
            if [[ "$new_boot_id" =~ ^[0-9a-f-]{36}$ ]] && [ "$new_boot_id" != "$boot_id" ]; then
                break
            fi
            sleep 5
        done
        if [[ "$new_boot_id" =~ ^[0-9a-f-]{36}$ ]] && [ "$new_boot_id" != "$boot_id" ]; then
            set +e
            remote_exec "$destination" "$port" 'pleb update --show' \
                >"$lane_dir/show-after-reboot.txt" 2>"$lane_dir/show-after-reboot.stderr"
            show_rc=$?
            set -e
            if [ "$show_rc" -eq 0 ]; then
                post_version="$(sed -n 's/^  PLEBIAN_OS_VERSION=\([^ ]*\).*/\1/p' \
                    "$lane_dir/show-after-reboot.txt" | head -n 1)"
            fi
            if [ "$post_version" = "$target" ]; then reboot_rc=0; fi
        fi
    fi
    printf '%s\n' "$reboot_rc" >"$lane_dir/reboot.exit"

    lane_runner_rc[$shape]="$runner_rc"
    lane_retrieve_rc[$shape]="$retrieve_rc"
    lane_checksum_rc[$shape]="$checksum_rc"
    lane_reboot_rc[$shape]="$reboot_rc"
    lane_post_version[$shape]="$post_version"
}

run_lane image "$image_guest" "$image_port" "$image_boot_id"
run_lane standalone "$standalone_guest" "$standalone_port" "$standalone_boot_id"

lane_pass=0
for shape in image standalone; do
    if [ "${lane_runner_rc[$shape]}" -eq 0 ] \
        && [ "${lane_retrieve_rc[$shape]}" -eq 0 ] \
        && [ "${lane_checksum_rc[$shape]}" -eq 0 ] \
        && [ "${lane_reboot_rc[$shape]}" -eq 0 ] \
        && [ "${lane_post_version[$shape]}" = "$target" ]; then
        lane_pass=$((lane_pass + 1))
    fi
done
overall_status=fail
if [ "$lane_pass" -eq 2 ]; then overall_status=pass; fi

export F109_HOST_FROM="$from" F109_HOST_TARGET="$target"
export F109_HOST_STATUS="$overall_status" F109_HOST_LANE_PASS="$lane_pass"
export F109_HOST_ISO_SHA256="$actual_iso_sha256"
export F109_HOST_BUILD_INFO_SHA256="$source_build_info_sha256"
export F109_HOST_OS_REF="$from_os_ref" F109_HOST_PLEB_REF="$from_pleb_ref"
export F109_HOST_KILIX_REF="$from_kilix_ref" F109_HOST_KILIX95_REF="$from_kilix95_ref"
export F109_HOST_IMAGE_MACHINE="$image_machine_id"
export F109_HOST_STANDALONE_MACHINE="$standalone_machine_id"
export F109_HOST_IMAGE_RUNNER="${lane_runner_rc[image]}"
export F109_HOST_IMAGE_RETRIEVE="${lane_retrieve_rc[image]}"
export F109_HOST_IMAGE_CHECKSUM="${lane_checksum_rc[image]}"
export F109_HOST_IMAGE_REBOOT="${lane_reboot_rc[image]}"
export F109_HOST_IMAGE_POST="${lane_post_version[image]}"
export F109_HOST_STANDALONE_RUNNER="${lane_runner_rc[standalone]}"
export F109_HOST_STANDALONE_RETRIEVE="${lane_retrieve_rc[standalone]}"
export F109_HOST_STANDALONE_CHECKSUM="${lane_checksum_rc[standalone]}"
export F109_HOST_STANDALONE_REBOOT="${lane_reboot_rc[standalone]}"
export F109_HOST_STANDALONE_POST="${lane_post_version[standalone]}"
python3 - "$report/report.json" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

def lane(prefix):
    return {
        "runner_exit": int(os.environ[f"F109_HOST_{prefix}_RUNNER"]),
        "evidence_retrieval_exit": int(os.environ[f"F109_HOST_{prefix}_RETRIEVE"]),
        "evidence_checksum_exit": int(os.environ[f"F109_HOST_{prefix}_CHECKSUM"]),
        "reboot_and_postcheck_exit": int(os.environ[f"F109_HOST_{prefix}_REBOOT"]),
        "post_reboot_version": os.environ[f"F109_HOST_{prefix}_POST"] or None,
    }

report = {
    "schema": "plebian-os.f109-release-hop-host-acceptance/v1",
    "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": os.environ["F109_HOST_STATUS"],
    "measured_not_adjudicated": True,
    "release_hop": {
        "from": os.environ["F109_HOST_FROM"],
        "to": os.environ["F109_HOST_TARGET"],
    },
    "starting_fixture": {
        "published_iso_sha256": os.environ["F109_HOST_ISO_SHA256"],
        "build_info_sha256": os.environ["F109_HOST_BUILD_INFO_SHA256"],
        "plebian_os_ref": os.environ["F109_HOST_OS_REF"],
        "pleb_ref": os.environ["F109_HOST_PLEB_REF"],
        "kilix_ref": os.environ["F109_HOST_KILIX_REF"],
        "kilix95_ref": os.environ["F109_HOST_KILIX95_REF"],
    },
    "guest_identity": {
        "distinct_machine_ids": 2,
        "distinct_machine_id_denominator": 2,
        "image_machine_id": os.environ["F109_HOST_IMAGE_MACHINE"],
        "standalone_machine_id": os.environ["F109_HOST_STANDALONE_MACHINE"],
    },
    "lanes": {
        "passed": int(os.environ["F109_HOST_LANE_PASS"]),
        "total": 2,
        "image": lane("IMAGE"),
        "standalone": lane("STANDALONE"),
    },
}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

(
    cd "$report"
    mapfile -d '' evidence_files < <(
        find . -type f ! -name SHA256SUMS -print0 | sort -z
    )
    sha256sum "${evidence_files[@]}" >SHA256SUMS
    sha256sum -c SHA256SUMS >/dev/null
)
evidence_count="$(wc -l <"$report/SHA256SUMS")"
printf 'acceptance-release-hop-host: %s %s -> %s; lanes %s/2; evidence checksums %s/%s at %s\n' \
    "${overall_status^^}" "$from" "$target" "$lane_pass" \
    "$evidence_count" "$evidence_count" "$report"
[ "$overall_status" = pass ]
