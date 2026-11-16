"""Static and refusal controls for F109's operator-run VM qualification lane."""

import hashlib
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "build" / "acceptance-release-hop.sh"
HOST_RUNNER = ROOT / "build" / "acceptance-release-hop-host.sh"
RELEASING = ROOT / "RELEASING.md"


class F109ReleaseHopAcceptanceRunnerTests(unittest.TestCase):
    @staticmethod
    def path_helpers():
        source = RUNNER.read_text()
        helpers = []
        for name in ("path_fingerprint", "engine_fingerprint", "resolve_installed_paths",
                     "select_installed_paths", "bound_engine_fingerprint"):
            body = source[source.index(name + "() {"):]
            helpers.append(body[:body.index("\n}\n") + 3])
        return "\n".join(helpers)

    @staticmethod
    def config_fixture(root):
        # Controlled installed-library boundary: the production selector must
        # call this module and consume persisted values, not its own defaults.
        # Integration with the selected real Pleb resolver is checked separately.
        lib = root / "lib"
        lib.mkdir(exist_ok=True)
        (lib / "common.sh").write_text(r'''
PLEB_ENV_USER="$PLEB_ROOT/persisted.env"
if [ -f "$PLEB_ENV_USER" ]; then . "$PLEB_ENV_USER"; fi
KILIX_BUILD_DIRECTORY="${KILIX_BUILD_DIRECTORY:-$PLEB_ROOT/build}"
KILIX_STATE_DIRECTORY="${KILIX_STATE_DIRECTORY:-$PLEB_ROOT/state}"
KILIX_PREBUILT_HOME="${KILIX_PREBUILT_HOME:-$PLEB_ROOT/prebuilt}"
GPU_TERMINAL_SETTINGS_FILE="$PLEB_ROOT/settings"
GPU_TERMINAL_SOURCE_HOME="$PLEB_ROOT/sources"
PLEB_STATE_HOME="$PLEB_ROOT/pleb-state"
PLEB_ENV_SYSTEM="$PLEB_ROOT/session"
PLEB_CLOSURE_SYSTEM="$PLEB_ROOT/closure"
PLEB_CLOSURE_USER="$PLEB_ROOT/user-closure"
KILIX_DIR="$PLEB_ROOT"
PLEB_DIR="$PLEB_ROOT"
''')

    def selected_fingerprint(self, root, after_selection="", *args):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("PLEB_", "KILIX_", "GPU_TERMINAL_"))}
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", self.path_helpers() +
             '\npleb_dir="$1"; select_installed_paths;\n' + after_selection +
             '\nbound_engine_fingerprint', "bash", str(root), *map(str, args)],
            env=env, capture_output=True, text=True, check=False,
        )

    def test_runner_exposes_both_required_shapes_and_exact_hop(self):
        source = RUNNER.read_text()
        self.assertEqual(
            source.count(
                '"${hop_command[@]}" update --to "$target" "${release_args[@]}" --yes --no-restart'
            ),
            4,
        )
        for token in (
            "--shape image|standalone",
            'case "$shape" in image|standalone)',
            '"${hop_command[@]}" update --to "$target" "${release_args[@]}" --yes --no-restart',
            '"${hop_command[@]}" update --to "$target" "${release_args[@]}" --dry-run --yes --no-restart',
            "PLEBIAN_OS_SELECT_TEST_FAIL_AFTER",
            "home-before.tsv",
            "home-after-failure.tsv",
            "home-after-success.tsv",
            "MANIFEST.sha256",
            'test ! -e /etc/pleb/session.env',
            'test ! -e "$source_home/plebian-os"',
            'test ! -e /usr/bin/plebian-os-update',
            '"installed-pleb-entrypoint-is-tested"',
            '"entrypoint-matches-participating-pleb-checkout"',
            '"starting-release-is-exact"',
            '"starting-pleb-ref-is-exact"',
            '"starting-kilix-ref-is-exact"',
            '"installed-$component-ref-matches-target"',
            '"image-build-info-matches-published-fixture"',
            '"image-build-info-is-install-predecessor"',
            '"installed-release-identity-is-from-release-tag"',
            '"selected-release-tag-object-is-staged"',
            '"rollback-restores-rc-closure-keys"',
            '"rollback-restores-rc-closure-bytes"',
            "update --rollback --yes --no-restart",
            "--from-release-tag",
            'cmp -s "$report/closure.pre-hop" "$closure_env"',
            '"${hop_command[@]}" update --to "$target" "${release_args[@]}" --yes --no-restart',
            'must "target-differs-from-installed-release"',
            '"rollback-restores-pre-hop-state"',
            '"restoring-hop-restores-post-hop-state"',
            "$label did not restore",
            '    for path in "$session_env" "$closure_env" "$settings_file" \\\n'
            '        /usr/bin/plebian-os-select-closure /usr/bin/plebian-os-update; do',
            '    printf \'head\\t%s\\t%s\\n\' "$pleb_dir" \\\n'
            '        "$(git -C "$pleb_dir" rev-parse --verify \'HEAD^{commit}\')" >>"$manifest"\n',
            '        printf \'head\\t%s\\t%s\\n\' "$os_dir" \\\n'
            '            "$(git -C "$os_dir" rev-parse --verify \'HEAD^{commit}\')" >>"$manifest"\n',
            '        assert_release_snapshot_restored rollback "$report/release-snapshot.pre-hop"',
            '        assert_release_snapshot_restored "restoring hop" "$report/release-snapshot.post-hop"',
            '    if [ "$show_ref" != "$ref" ]; then',
            '        must "installed-closure-matches-published-rc-manifest" "$from_release_manifest" \\\n'
            '            assert_pre_hop_manifest "$closure_env"',
            'printf \'fingerprint\\t%s\\t%s\\n\' "$release_state"',
            'printf \'engine\\t%s\\t%s\\n\' "$engine_build"',
            '            engine)\n'
            '                actual="$(bound_engine_fingerprint | sha256sum | awk \'{print $1}\')" || return 1',
            '        selection_tag_state="$(assert_recorded_selection_tag /var/lib/plebian-os "$from_release_tag_object")" \\\n',
            "not-verified unreadable",
            "assert_pre_hop_release_identity",
            "assert_post_hop_release_identity",
            "closure_keys_match",
            '"dry-run-preserves-engine-generation"',
            '"failure-restores-engine-generation"',
            '"declared-sentinel-corpus-is-complete"',
            '"induced-closure-boundary-was-reached"',
            '"dirty-image-refusal-is-the-cleanliness-guard"',
            '"dirty-refusal-clears-incomplete-transition"',
            '${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}',
            '"dry_run_command_denominator": 1',
            '"successful_hop_command_denominator": 1',
        ):
            self.assertIn(token, source)

    def test_explicit_rc_identity_is_validated_before_guest_or_host_work(self):
        for runner in (RUNNER, HOST_RUNNER):
            for tag in ("v0.2.3-rc0", "v0.2.3-rc01", "v0.2.2-rc1", "v0.2.3-beta1"):
                with self.subTest(runner=runner.name, tag=tag):
                    args = [str(runner), "--from", "0.2.2", "--target", "0.2.3", "--release-tag", tag]
                    if runner == RUNNER:
                        args += ["--shape", "image", "--disposable-vm"]
                    result = subprocess.run(args, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("--release-tag must be the exact target", result.stderr)

    def test_help_is_non_mutating_and_documents_the_guest_boundary(self):
        result = subprocess.run(
            [str(RUNNER), "--help"], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--disposable-vm", result.stdout)
        self.assertIn("outside", result.stdout)

    def test_runner_refuses_before_creating_a_report_without_vm_consent(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report"
            result = subprocess.run(
                [
                    str(RUNNER),
                    "--shape", "standalone",
                    "--target", "0.2.1",
                    "--report", str(report),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without --disposable-vm", result.stderr)
            self.assertFalse(report.exists())

    def test_preservation_requires_exact_original_or_collision_sidecar_bytes(self):
        source = RUNNER.read_text()
        helper = source[source.index("preserved_sentinel_path() {"):]
        helper = helper[:helper.index("\n}\n") + 3]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "README.md"
            preserved = b"operator bytes\x00\xff\n"
            expected = hashlib.sha256(preserved).hexdigest()

            def check(kind="modified-tracked"):
                return subprocess.run(
                    ["bash", "-c", helper + '\npreserved_sentinel_path "$@"',
                     "bash", str(path), expected, kind],
                    capture_output=True, text=True, check=False,
                )

            path.write_bytes(preserved)
            self.assertEqual(check().stdout.strip(), str(path))
            path.write_bytes(b"new upstream bytes\n")
            self.assertNotEqual(check().returncode, 0)
            sidecar = path.with_name(path.name + ".local")
            sidecar.write_bytes(preserved)
            self.assertEqual(check().stdout.strip(), str(sidecar))
            self.assertNotEqual(check("untracked").returncode, 0)
            numbered = path.with_name(path.name + ".local.1")
            sidecar.rename(numbered)
            self.assertEqual(check().stdout.strip(), str(numbered))
            numbered.write_bytes(b"corrupt\n")
            self.assertNotEqual(check().returncode, 0)
            numbered.unlink()
            numbered.symlink_to(path)
            path.write_bytes(b"new upstream bytes\n")
            self.assertNotEqual(check().returncode, 0)

    def test_engine_fingerprint_detects_generation_and_stamp_changes(self):
        source = RUNNER.read_text()
        helpers = []
        for name in ("path_fingerprint", "engine_fingerprint"):
            helper = source[source.index(name + "() {"):]
            helpers.append(helper[:helper.index("\n}\n") + 3])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build, state = root / "build", root / "state"
            state.mkdir()
            for generation in ("first", "second"):
                leaf = build / "generations" / ("build." + generation)
                launchers = leaf / "src/kitty/launcher"
                launchers.mkdir(parents=True)
                for path in (leaf / "source-id", launchers / "kitty", launchers / "kitten"):
                    path.write_text(generation + "\n")
            (build / "current").symlink_to("generations/build.second")
            (build / "previous").symlink_to("generations/build.first")
            stamp = state / "fork-built-ref"
            stamp.write_text("canonical stamp\n")

            def fingerprint():
                return subprocess.check_output(
                    ["bash", "-euo", "pipefail", "-c", "\n".join(helpers) +
                     '\nengine_fingerprint "$1" "$2"', "bash", str(build), str(state)],
                    text=True,
                )

            baseline = fingerprint()
            # The historical check observed this absent path in every case.
            self.assertFalse((state / "current").exists())
            for path in (build / "current", build / "previous", stamp,
                         build / "current/source-id", build / "current/src/kitty/launcher/kitty",
                         build / "previous/src/kitty/launcher/kitten"):
                with self.subTest(path=path):
                    if path.is_symlink():
                        target = path.readlink()
                        path.unlink()
                        path.symlink_to("generations/build.missing")
                        self.assertNotEqual(fingerprint(), baseline)
                        path.unlink()
                        path.symlink_to(target)
                    else:
                        original = path.read_bytes()
                        path.write_bytes(b"changed\n")
                        self.assertNotEqual(fingerprint(), baseline)
                        path.write_bytes(original)
                    self.assertEqual(fingerprint(), baseline)

    def test_persisted_only_paths_select_real_engine_and_prebuilt_payloads(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.config_fixture(root)
            engine = root / "operator's relocated engine"
            build, state, prebuilt = engine / "build", engine / "state", engine / "prebuilt"
            launchers = build / "generations" / "one" / "src/kitty/launcher"
            launchers.mkdir(parents=True)
            state.mkdir()
            (prebuilt / "bin").mkdir(parents=True)
            (prebuilt / "native-kitty").write_text("before\n")
            (prebuilt / "bin/kitty").symlink_to("../native-kitty")
            (build / "current").symlink_to("generations/one")
            payloads = [launchers / "kitty", launchers / "kitten",
                        state / "fork-built-ref", prebuilt / "bin/kitty", prebuilt / "bin/kitten"]
            for path in payloads:
                path.write_text("before\n")
            (root / "persisted.env").write_text(
                "printf 'configuration notice\\n'\n" + "\n".join(
                    f"{name}={shlex.quote(str(value))}" for name, value in (
                        ("KILIX_BUILD_DIRECTORY", build), ("KILIX_STATE_DIRECTORY", state),
                        ("KILIX_PREBUILT_HOME", prebuilt))) + "\n"
            )
            before = self.selected_fingerprint(root)
            self.assertEqual(before.returncode, 0, before.stderr)
            self.assertIn("file:", before.stdout)
            self.assertIn("configuration notice", before.stderr)
            self.assertFalse((root / "build").exists(), "default engine path remains absent")
            for path in payloads:
                with self.subTest(path=path):
                    path.write_text("changed\n")
                    changed = self.selected_fingerprint(root)
                    self.assertEqual(changed.returncode, 0, changed.stderr)
                    self.assertNotEqual(changed.stdout, before.stdout)
                    path.write_text("before\n")
                    self.assertEqual(self.selected_fingerprint(root).stdout, before.stdout)

    def test_bound_paths_refuse_persisted_route_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.config_fixture(root)
            (root / "persisted.env").write_text("")
            result = self.selected_fingerprint(
                root, 'printf "KILIX_BUILD_DIRECTORY=%q\\n" "$2" >>"$pleb_dir/persisted.env"',
                root / "different-build",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("effective installed paths changed", result.stderr)

    def test_path_selection_refuses_unbound_or_unsupported_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertNotEqual(self.selected_fingerprint(root).returncode, 0)
            self.config_fixture(root)
            for value in ("relative-build", "relative:/build", str(root / "line\nbreak")):
                with self.subTest(value=value):
                    (root / "persisted.env").write_text(
                        "KILIX_BUILD_DIRECTORY=" + shlex.quote(value) + "\n"
                    )
                    self.assertNotEqual(self.selected_fingerprint(root).returncode, 0)

    def test_reboot_verifier_rejects_same_version_checkout_and_sentinel_drift(self):
        source = RUNNER.read_text()
        helpers = []
        for name in ("path_fingerprint", "engine_fingerprint", "resolve_installed_paths",
                     "select_installed_paths", "bound_engine_fingerprint",
                     "preserved_sentinel_path", "write_reboot_verifier"):
            helper = source[source.index(name + "() {"):]
            helpers.append(helper[:helper.index("\n}\n") + 3])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.config_fixture(root)
            git = ["git", "-C", td]
            subprocess.run(git + ["init", "-q"], check=True)
            (root / "VERSION").write_text("0.2.2\n")
            subprocess.run(git + ["add", "VERSION"], check=True)
            refs = []
            for message in ("old", "target"):
                subprocess.run(git + ["-c", "user.name=test", "-c",
                                      "user.email=test@example.invalid", "commit", "-qm",
                                      message, "--allow-empty"], check=True)
                refs.append(subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip())
            show = root / "show-after.txt"
            show.write_text(f"  PLEBIAN_OS_VERSION=0.2.2\n  PLEB_REF={refs[1]}\n  KILIX_REF={refs[1]}\n"
                            f"  PLEBIAN_OS_REF={refs[1]}\n  KILIX95_REF={refs[1]}\n")
            os_source = root / "os-source"
            subprocess.run(["git", "clone", "-q", "--no-hardlinks", td, str(os_source)], check=True)
            pleb = root / "pleb"
            pleb.write_text('#!/bin/sh\ncat "$(dirname "$0")/show-after.txt"\n')
            pleb.chmod(0o700)
            sentinel = root / "operator's file"
            sentinel.write_bytes(b"operator bytes\x00\xff")
            prebuilt = root / "prebuilt/bin/kitty"
            prebuilt.parent.mkdir(parents=True)
            prebuilt.write_text("selected engine\n")
            sentinels = root / "sentinels.tsv"
            sentinels.write_text(f"{sentinel}\t{hashlib.sha256(sentinel.read_bytes()).hexdigest()}\tuntracked\n")
            script = "\n".join(helpers) + r'''
report="$1"; pleb_bin="$report/pleb"; pleb_dir="$report"; kilix_dir="$report"
session_env="$report/session"; closure_env="$report/closure"; settings_file="$report/settings"
select_installed_paths; sentinels="$report/sentinels.tsv"
release_tag=v0.2.2-rc1
mkdir -p "$(dirname "$release_state")"
printf '%s\n' 0.2.2 commit object digest "$release_tag" >"$release_state"
target_components=(pleb kilix os kilix95); declare -A image_resolved_paths=()
os_dir="$report/os-source"; kilix95_dir="$report"
write_reboot_verifier "$report/verify.sh"
'''
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("PLEB_", "KILIX_", "GPU_TERMINAL_"))}
            subprocess.run(["bash", "-euo", "pipefail", "-c", script, "bash", td],
                           env=env, check=True)

            def verify():
                return subprocess.run(["bash", str(root / "verify.sh")],
                                      env=env, capture_output=True).returncode

            self.assertEqual(verify(), 0)
            release_state = root / "pleb-state/release-hop/active"
            exact_state = release_state.read_bytes()
            release_state.write_bytes(exact_state.replace(b"v0.2.2-rc1", b"v0.2.2-rc2"))
            self.assertNotEqual(verify(), 0, "same numeric version must not hide another RC tag")
            release_state.write_bytes(exact_state.replace(b"object", b"changed-object"))
            self.assertNotEqual(verify(), 0, "tag spelling must not hide another tag object")
            release_state.write_bytes(exact_state)
            self.assertEqual(verify(), 0)
            prebuilt.write_text("changed engine\n")
            self.assertNotEqual(verify(), 0, "reboot must check the resolved prebuilt engine")
            prebuilt.write_text("selected engine\n")
            self.assertEqual(verify(), 0)
            persisted = root / "persisted.env"
            persisted.write_text("KILIX_BUILD_DIRECTORY=" + shlex.quote(str(root / "other-build")) + "\n")
            self.assertNotEqual(verify(), 0, "reboot must resolve the installed path binding again")
            persisted.unlink()
            self.assertEqual(verify(), 0)
            subprocess.run(git + ["checkout", "-q", "--detach", refs[0]], check=True)
            self.assertNotEqual(verify(), 0, "same VERSION must not hide a stale checkout")
            subprocess.run(git + ["checkout", "-q", "--detach", refs[1]], check=True)
            self.assertEqual(verify(), 0)
            subprocess.run(["git", "-C", str(os_source), "checkout", "-q", "--detach", refs[0]], check=True)
            self.assertNotEqual(verify(), 0, "image OS revision must also survive reboot")
            subprocess.run(["git", "-C", str(os_source), "checkout", "-q", "--detach", refs[1]], check=True)
            self.assertEqual(verify(), 0)
            sentinel.write_bytes(b"changed")
            self.assertNotEqual(verify(), 0)

    def test_selected_target_cannot_hide_an_unchanged_installed_checkout(self):
        source = RUNNER.read_text()
        helper = source[source.index("verify_installed_target_ref() {"):]
        helper = helper[:helper.index("\n}\n") + 3]
        with tempfile.TemporaryDirectory() as td:
            checkout = Path(td)
            git = ["git", "-C", td]
            subprocess.run(git + ["init", "-q"], check=True)
            refs = []
            for contents in ("old\n", "target\n"):
                (checkout / "state").write_text(contents)
                subprocess.run(git + ["add", "state"], check=True)
                subprocess.run(git + ["-c", "user.name=test", "-c",
                                      "user.email=test@example.invalid", "commit", "-qm", contents],
                               check=True)
                refs.append(subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip())

            def check(selected):
                return subprocess.run(
                    ["bash", "-e", "-c",
                     'die() { exit 1; }; must() { shift 2; "$@"; };\n' + helper +
                     '\nverify_installed_target_ref pleb "$1" "$2"',
                     "bash", td, selected], capture_output=True, text=True, check=False,
                )

            self.assertEqual(check(refs[1]).returncode, 0)
            subprocess.run(git + ["checkout", "-q", "--detach", refs[0]], check=True)
            self.assertNotEqual(check(refs[1]).returncode, 0)
            self.assertNotEqual(check("").returncode, 0)

    def test_runner_requires_exact_starting_fixture_before_writing_report(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report"
            result = subprocess.run(
                [
                    str(RUNNER),
                    "--shape", "standalone",
                    "--target", "0.2.1",
                    "--report", str(report),
                    "--disposable-vm",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--from must be X.Y.Z", result.stderr)
            self.assertFalse(report.exists())

    def test_image_operator_resolution_preserves_ten_files_and_refuses_bad_hash(self):
        source = RUNNER.read_text()
        helper = source[source.index("resolve_image_checkout_fixtures() {"):]
        helper = helper[:helper.index("\n}\n") + 3]
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                repos = [base / "pleb", base / "kilix"]
                records = []
                for repo in repos:
                    repo.mkdir()
                    git = ["git", "-C", str(repo)]
                    subprocess.run(git + ["init", "-q"], check=True)
                    readme = repo / "README.md"
                    readme.write_text("release bytes\n")
                    subprocess.run(git + ["add", "README.md"], check=True)
                    subprocess.run(git + ["-c", "user.name=test", "-c", "user.email=test@example.invalid",
                                          "commit", "-qm", "fixture"], check=True)
                    readme.write_bytes(b"owner readme\x00\xff\n")
                    records.append((readme, "modified-tracked", readme.read_bytes()))
                (repos[0] / "scripts").mkdir()
                for index in range(7):
                    path = repos[0] / "scripts" / f"camera-{index}.sh"
                    path.write_text(f"#!/bin/sh\necho {index}\n")
                    path.chmod(0o700)
                    records.append((path, "untracked", path.read_bytes()))
                binary = repos[1] / "operator.bin"
                binary.write_bytes(b"operator\x00\xff")
                records.append((binary, "untracked", binary.read_bytes()))
                report = base / "report"
                report.mkdir(mode=0o700)
                sentinels = report / "sentinels.tsv"
                sentinels.write_text("".join(
                    f"{path}\t{'0' * 64 if corrupt and index == 0 else hashlib.sha256(data).hexdigest()}\t{kind}\n"
                    for index, (path, kind, data) in enumerate(records)
                ))
                result = subprocess.run(
                    ["bash", "-euo", "pipefail", "-c",
                     'die() { printf "%s\\n" "$*" >&2; exit 1; };\n' + helper +
                     '\nreport="$1"; pleb_dir="$2"; kilix_dir="$3"; sentinels="$report/sentinels.tsv"; '
                     'declare -A image_resolved_paths=(); image_operator_files=0; '
                     'resolve_image_checkout_fixtures; [ "$image_operator_files" = 10 ]; '
                     '[ "${#image_resolved_paths[@]}" = 10 ]',
                     "bash", str(report), str(repos[0]), str(repos[1])],
                    capture_output=True, text=True, check=False,
                )
                if corrupt:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("verification failed", result.stderr)
                    for path, _, data in records:
                        self.assertEqual(path.read_bytes(), data)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    mapping = [line.split("\t") for line in (report / "operator-resolution.tsv").read_text().splitlines()]
                    self.assertEqual(len(mapping), 10)
                    for original, saved, expected, kind in mapping:
                        self.assertEqual(hashlib.sha256(Path(saved).read_bytes()).hexdigest(), expected)
                        self.assertEqual(Path(saved).parent, report, "evidence extraction permits flat regular files")
                        if kind == "modified-tracked":
                            self.assertEqual(Path(original).read_text(), "release bytes\n")
                        else:
                            self.assertFalse(Path(original).exists())
                    for repo in repos:
                        self.assertEqual(subprocess.check_output(
                            ["git", "-C", str(repo), "status", "--porcelain"], text=True), "")

    def test_host_controller_binds_two_guests_artifact_and_reboot(self):
        source = HOST_RUNNER.read_text()
        for token in (
            "StrictHostKeyChecking=yes",
            "BatchMode=yes",
            "/etc/machine-id",
            "/proc/sys/kernel/random/boot_id",
            "/plebian-os/build-info.env",
            "source ISO checksum mismatch",
            "distinct VMs",
            "sudo -n systemctl reboot",
            "sha256sum -c SHA256SUMS",
            '"total": 2',
            "--from-release-tag",
            "--release-tag-object",
            "--predecessor-sha256sums",
            "--from-release-manifest",
            "published_build_info_sha256",
            "published_named_sha256",
            "release manifest checksum mismatch",
            "source checksum file must name the release manifest exactly once",
            '[ "$actual_manifest_sha256" = "$manifest_sha256" ]',
            'die "source ISO tag object does not match --from-release-tag-object"',
            "PLEBIAN_OS_RELEASE_TAG=$release_tag",
            "installed-closure",
            "source_iso_names_installed_rc",
            "same-version finalization uses the installed release CLI",
        ):
            self.assertIn(token, source)

        result = subprocess.run(
            [str(HOST_RUNNER), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("passing run always executes and verifies 2/2", result.stdout)

    def test_release_procedure_invokes_two_vm_controller(self):
        text = RELEASING.read_text()
        self.assertEqual(text.count("acceptance-release-hop-host.sh"), 2)
        self.assertIn("--from <previous-x.y.z> --target <x.y.z>", text)
        self.assertIn("--from 0.2.3 --target 0.2.3", text)
        self.assertIn("--release-tag v0.2.3 --from-release-tag v0.2.3-rc9", text)
        self.assertIn("--from-release-tag-object 532d238f65c4bc1dc82a817bab01a467e287ba16", text)
        self.assertIn("--predecessor-sha256sums", text)
        self.assertIn("cannot tell the installed RC from the final", text)
        self.assertIn("requires 2/2 distinct VM machine", text)
        self.assertIn("both 2/2 guest evidence sets", text)

    def _run_runner(self, runner, extra):
        return subprocess.run(
            [str(runner), *extra], capture_output=True, text=True, check=False,
        )

    def test_same_version_finalization_accepts_rc_to_its_stable_final(self):
        commit = "a" * 40
        for runner in (RUNNER, HOST_RUNNER):
            with self.subTest(runner=runner.name):
                extra = ["--from", "0.2.3", "--target", "0.2.3",
                         "--release-tag", "v0.2.3", "--from-release-tag", "v0.2.3-rc9",
                         "--from-release-tag-object", "b" * 40,
                         "--release-tag-object", "c" * 40]
                if runner is RUNNER:
                    extra = ["--shape", "standalone", "--disposable-vm", *extra,
                             "--expected-release-commit", commit, "--report", "/tmp/f109-unused"]
                result = self._run_runner(runner, extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("must differ", result.stderr)
                self.assertNotIn("same-version hop requires", result.stderr)
                self.assertNotIn("only valid when --from equals --target", result.stderr)
                if runner is RUNNER:
                    self.assertIn("starting Pleb and Kilix refs", result.stderr)
                else:
                    self.assertIn("guest destinations", result.stderr)

    def test_plain_same_version_hop_is_refused(self):
        cases = (
            ["--from", "0.2.3", "--target", "0.2.3"],
            ["--from", "0.2.3", "--target", "0.2.3", "--release-tag", "v0.2.3"],
            ["--from", "0.2.3", "--target", "0.2.3", "--from-release-tag", "v0.2.3-rc9"],
        )
        for runner in (RUNNER, HOST_RUNNER):
            for extra in cases:
                with self.subTest(runner=runner.name, extra=extra):
                    args = list(extra)
                    if runner is RUNNER:
                        args = ["--shape", "standalone", "--disposable-vm", *args,
                                "--report", "/tmp/f109-unused"]
                    result = self._run_runner(runner, args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("same-version hop requires", result.stderr)

    def test_wrong_from_release_tag_is_refused(self):
        bad_tags = ("v0.2.3-rc0", "v0.2.3-rc01", "v0.2.3", "v0.2.2-rc9", "v0.2.3-rc")
        for runner in (RUNNER, HOST_RUNNER):
            for tag in bad_tags:
                with self.subTest(runner=runner.name, tag=tag):
                    extra = ["--from", "0.2.3", "--target", "0.2.3",
                             "--release-tag", "v0.2.3", "--from-release-tag", tag]
                    if runner is RUNNER:
                        extra = ["--shape", "standalone", "--disposable-vm", *extra,
                                 "--expected-release-commit", "a" * 40,
                                 "--report", "/tmp/f109-unused"]
                    result = self._run_runner(runner, extra)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("--from-release-tag must name the installed RC", result.stderr)

    def test_rc_to_rc_same_version_hop_is_refused(self):
        for runner in (RUNNER, HOST_RUNNER):
            extra = ["--from", "0.2.3", "--target", "0.2.3",
                     "--release-tag", "v0.2.3-rc9", "--from-release-tag", "v0.2.3-rc8"]
            if runner is RUNNER:
                extra = ["--shape", "standalone", "--disposable-vm", *extra,
                         "--report", "/tmp/f109-unused"]
            result = self._run_runner(runner, extra)
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertIn("same-version hop requires", result.stderr)

    def test_same_version_finalization_refuses_a_bootstrap_driver(self):
        for runner in (RUNNER, HOST_RUNNER):
            extra = ["--from", "0.2.3", "--target", "0.2.3",
                     "--release-tag", "v0.2.3", "--from-release-tag", "v0.2.3-rc9",
                     "--bootstrap-driver", "/var/tmp/rc9-driver/bin/pleb-release-hop",
                     "--bootstrap-driver-ref", "b" * 40]
            if runner is RUNNER:
                extra = ["--shape", "standalone", "--disposable-vm", *extra,
                         "--expected-release-commit", "c" * 40,
                         "--report", "/tmp/f109-unused"]
            result = self._run_runner(runner, extra)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("omit the bootstrap driver", result.stderr)

    def test_different_version_hop_rejects_from_release_tag(self):
        for runner in (RUNNER, HOST_RUNNER):
            extra = ["--from", "0.2.2", "--target", "0.2.3",
                     "--release-tag", "v0.2.3-rc9", "--from-release-tag", "v0.2.2-rc1"]
            if runner is RUNNER:
                extra = ["--shape", "standalone", "--disposable-vm", *extra,
                         "--report", "/tmp/f109-unused"]
            result = self._run_runner(runner, extra)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("only valid when --from equals --target", result.stderr)

    def _bash_function(self, source, name):
        body = source[source.index(name + "() {"):]
        return body[:body.index("\n}\n") + 3]

    def test_pre_hop_identity_accepts_recorded_and_unrecorded_rc9(self):
        helper = "\n".join(
            self._bash_function(RUNNER.read_text(), name)
            for name in (
                "closure_key", "closure_shell_value", "load_closure_identity",
                "assert_pre_hop_release_identity",
            )
        )
        commit = "a" * 40
        rc_object = "b" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            unrecorded = root / "unrecorded.env"
            unrecorded.write_text(
                f"PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_REF={commit}\nPLEB_REF={'c' * 40}\n"
            )
            recorded = root / "recorded.env"
            recorded.write_text(
                "PLEBIAN_OS_VERSION=0.2.3\n"
                f"PLEBIAN_OS_REF={commit}\n"
                "PLEBIAN_OS_RELEASE_TAG=v0.2.3-rc9\n"
                f"PLEBIAN_OS_RELEASE_TAG_OBJECT={rc_object}\n"
            )
            object_only = root / "object.env"
            object_only.write_text(
                f"PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_REF={commit}\n"
                f"PLEBIAN_OS_RELEASE_TAG_OBJECT={rc_object}\n"
            )

            def check(path, tag, expected_object=""):
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nassert_pre_hop_release_identity "$1" "$2" "$3" "$4"',
                     "bash", str(path), tag, commit, expected_object],
                    capture_output=True, text=True, check=False,
                )

            self.assertEqual(check(unrecorded, "v0.2.3-rc9").returncode, 0)
            self.assertEqual(check(recorded, "v0.2.3-rc9", rc_object).returncode, 0)
            self.assertEqual(check(object_only, "v0.2.3-rc9", rc_object).returncode, 0)
            wrong = check(recorded, "v0.2.3-rc8", rc_object)
            self.assertNotEqual(wrong.returncode, 0)
            self.assertIn("expected v0.2.3-rc8", wrong.stderr)
            wrong_object = check(recorded, "v0.2.3-rc9", "d" * 40)
            self.assertNotEqual(wrong_object.returncode, 0)
            self.assertIn("installed tag object", wrong_object.stderr)
            moved = check(unrecorded, "v0.2.3-rc9")
            unrecorded.write_text(unrecorded.read_text().replace(commit, "e" * 40))
            drifted = check(unrecorded, "v0.2.3-rc9")
            self.assertEqual(moved.returncode, 0)
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("unrecorded closure commit", drifted.stderr)
            unpublished = check(recorded, "v0.2.3-rc9", "")
            self.assertNotEqual(unpublished.returncode, 0)
            self.assertIn("published object", unpublished.stderr)
            forged = root / "forged.env"
            forged.write_text(
                f"PLEBIAN_OS_REF={commit}\n PLEBIAN_OS_REF={'e' * 40}\n"
            )
            disagreed = check(forged, "v0.2.3-rc9")
            self.assertNotEqual(disagreed.returncode, 0)
            self.assertIn("disagree on PLEBIAN_OS_REF", disagreed.stderr)
            exported = root / "exported.env"
            exported.write_text(
                f"PLEBIAN_OS_REF={commit}\nexport PLEBIAN_OS_REF={'e' * 40}\n"
            )
            self.assertNotEqual(check(exported, "v0.2.3-rc9").returncode, 0)
            appended = root / "appended.env"
            appended.write_text(f"PLEBIAN_OS_REF={commit}\nPLEBIAN_OS_REF+=x\n")
            self.assertNotEqual(check(appended, "v0.2.3-rc9").returncode, 0)

    def test_post_hop_refuses_a_tag_object_mismatch(self):
        helper = "\n".join(
            self._bash_function(RUNNER.read_text(), name)
            for name in ("closure_key", "assert_post_hop_release_identity")
        )
        final_object = "f" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            closure = root / "closure.env"
            closure.write_text(
                "PLEBIAN_OS_VERSION=0.2.3\n"
                f"PLEBIAN_OS_REF={'1' * 40}\n"
                "PLEBIAN_OS_RELEASE_TAG=v0.2.3\n"
                f"PLEBIAN_OS_RELEASE_TAG_OBJECT={final_object}\n"
            )
            active = root / "active"
            active.write_text(
                "0.2.3\n" + ("2" * 40) + f"\n{final_object}\n" + ("3" * 64) + "\nv0.2.3\n"
            )

            def check(published=""):
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nassert_post_hop_release_identity "$1" "$2" v0.2.3 "$3"',
                     "bash", str(closure), str(active), published],
                    capture_output=True, text=True, check=False,
                )

            self.assertEqual(check().returncode, 0, check().stderr)
            self.assertEqual(check(final_object).returncode, 0, check(final_object).stderr)
            published_mismatch = check("9" * 40)
            self.assertNotEqual(published_mismatch.returncode, 0)
            self.assertIn("expected published", published_mismatch.stderr)
            active.write_text(active.read_text().replace(final_object, "4" * 40))
            mismatch = check()
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("tag-object mismatch", mismatch.stderr)
            active.write_text(active.read_text().replace("4" * 40, final_object))
            closure.write_text(closure.read_text().replace(final_object, "5" * 40))
            mismatch = check()
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("tag-object mismatch", mismatch.stderr)
            closure.write_text(closure.read_text().replace("5" * 40, final_object))
            lines = active.read_text().splitlines()
            lines[4] = "v0.2.3-rc9"
            active.write_text("\n".join(lines) + "\n")
            staged = check()
            self.assertNotEqual(staged.returncode, 0)
            self.assertIn("staged release tag", staged.stderr)
            lines[4] = "v0.2.3"
            active.write_text("\n".join(lines) + "\n")
            closure.write_text(closure.read_text().replace(
                "PLEBIAN_OS_RELEASE_TAG=v0.2.3", "PLEBIAN_OS_RELEASE_TAG=v0.2.3-rc9"))
            selected = check()
            self.assertNotEqual(selected.returncode, 0)
            self.assertIn("selected release tag", selected.stderr)

    def test_rollback_refuses_a_closure_mismatch(self):
        helper = self._bash_function(RUNNER.read_text(), "closure_keys_match")
        before_text = (
            "PLEBIAN_OS_VERSION=0.2.3\n"
            f"PLEBIAN_OS_REF={'a' * 40}\n"
            "PLEB_REF=" + "b" * 40 + "\n"
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            before = root / "before.env"
            after = root / "after.env"
            before.write_text(before_text)
            after.write_text(before_text)

            def check():
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nclosure_keys_match "$1" "$2"',
                     "bash", str(before), str(after)],
                    capture_output=True, text=True, check=False,
                )

            self.assertEqual(check().returncode, 0, check().stderr)
            after.write_text(
                before_text + "PLEBIAN_OS_RELEASE_TAG=v0.2.3\n"
                f"PLEBIAN_OS_RELEASE_TAG_OBJECT={'c' * 40}\n"
            )
            added = check()
            self.assertNotEqual(added.returncode, 0)
            self.assertIn("PLEBIAN_OS_RELEASE_TAG_OBJECT", added.stderr)
            after.write_text(before_text.replace("b" * 40, "d" * 40))
            changed = check()
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn("changed PLEB_REF", changed.stderr)

    def test_source_iso_names_the_installed_rc_or_refuses(self):
        helper = self._bash_function(HOST_RUNNER.read_text(), "source_iso_names_installed_rc")
        rc_object = "e" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def check(text, tag="v0.2.3-rc9"):
                path = root / "build-info.env"
                path.write_text(text)
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nsource_iso_names_installed_rc "$1" "$2"',
                     "bash", str(path), tag],
                    capture_output=True, text=True, check=False,
                )

            rc9 = check(
                "PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_REF=v0.2.3-rc9\n"
                f"PLEBIAN_OS_COMMIT={'a' * 40}\n"
            )
            self.assertEqual(rc9.returncode, 0, rc9.stderr)
            self.assertEqual(rc9.stdout, "")
            recorded = check(
                "PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_REF=v0.2.3-rc9\n"
                "PLEBIAN_OS_RELEASE_TAG=v0.2.3-rc9\n"
                f"PLEBIAN_OS_RELEASE_TAG_OBJECT={rc_object}\n"
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            self.assertEqual(recorded.stdout.strip(), rc_object)
            final = check("PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_REF=v0.2.3\n")
            self.assertNotEqual(final.returncode, 0)
            other_rc = check(
                "PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_REF=v0.2.3-rc8\n",
                "v0.2.3-rc9",
            )
            self.assertNotEqual(other_rc.returncode, 0)

    def test_image_binding_uses_the_closure_for_an_upgraded_guest(self):
        helper = self._bash_function(HOST_RUNNER.read_text(), "image_identity_binding")
        iso_hash = "1" * 64
        older_hash = "2" * 64

        def binding(same_version, installed, source, predecessor=""):
            return subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\nimage_identity_binding "$1" "$2" "$3" "$4"',
                 "bash", same_version, installed, source, predecessor],
                capture_output=True, text=True, check=False,
            )

        upgraded = binding("1", older_hash, iso_hash, older_hash)
        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        self.assertEqual(upgraded.stdout.strip(), "installed-closure")
        unbound = binding("1", older_hash, iso_hash)
        self.assertNotEqual(unbound.returncode, 0)
        fresh = binding("1", iso_hash, iso_hash)
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.assertEqual(fresh.stdout.strip(), "source-iso")
        ordinary = binding("0", iso_hash, iso_hash)
        self.assertEqual(ordinary.returncode, 0, ordinary.stderr)
        self.assertEqual(ordinary.stdout.strip(), "source-iso")
        rejected = binding("0", older_hash, iso_hash)
        self.assertNotEqual(rejected.returncode, 0)

    def test_predecessor_build_info_rejects_rc8_dev_and_hand_edits(self):
        helper = "\n".join([
            self._bash_function(RUNNER.read_text(), "classify_installed_build_info"),
            self._bash_function(HOST_RUNNER.read_text(), "published_build_info_sha256"),
        ])
        rc9 = "1" * 64
        predecessor = "2" * 64
        rc8 = "3" * 64
        dev = "4" * 64
        hand_edited = "2" * 63 + "0"

        def classify(installed, predecessor_hash=predecessor):
            return subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\nclassify_installed_build_info "$1" "$2" "$3"',
                 "bash", installed, rc9, predecessor_hash],
                capture_output=True, text=True, check=False,
            )

        upgraded = classify(predecessor)
        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        self.assertEqual(upgraded.stdout.strip(), "installed-closure")
        fresh = classify(rc9)
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.assertEqual(fresh.stdout.strip(), "source-iso")
        for label, installed in (("rc8", rc8), ("dev", dev), ("hand-edited", hand_edited)):
            with self.subTest(label=label):
                refused = classify(installed)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("neither the source ISO nor the published predecessor", refused.stderr)
        with tempfile.TemporaryDirectory() as td:
            sums = Path(td) / "SHA256SUMS"
            sums.write_text(
                f"{predecessor}  plebian-os-0.2.2-build-info.env\n"
                f"{'a' * 64}  plebian-os-0.2.2-amd64.iso\n"
            )
            parsed = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\npublished_build_info_sha256 "$1"', "bash", str(sums)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(parsed.returncode, 0, parsed.stderr)
            self.assertEqual(parsed.stdout.strip(), predecessor)
            sums.write_text(f"{'b' * 64}  plebian-os-0.2.2-amd64.iso\n")
            missing = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\npublished_build_info_sha256 "$1"', "bash", str(sums)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            sums.write_text(
                f"{predecessor}  plebian-os-0.2.2-build-info.env\n"
                f"{'c' * 64}  other-build-info.env\n"
            )
            several = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\npublished_build_info_sha256 "$1"', "bash", str(sums)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(several.returncode, 0)

    def test_rollback_refuses_a_partial_machine_restore(self):
        helper = "\n".join(
            self._bash_function(RUNNER.read_text(), name)
            for name in ("path_fingerprint", "assert_release_snapshot_restored")
        )

        def fingerprint(path):
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\npath_fingerprint "$1"', "bash", str(path)],
                capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()

        def compare(manifest, label):
            return subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\nassert_release_snapshot_restored "$1" "$2"',
                 "bash", label, str(manifest)],
                capture_output=True, text=True, check=False,
            )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            session = root / "session.env"
            closure = root / "closure.env"
            selector = root / "plebian-os-select-closure"
            updater = root / "plebian-os-update"
            pleb = root / "pleb"
            for path, text in (
                (session, "session-rc\n"),
                (closure, "closure-rc\n"),
                (selector, "selector-rc\n"),
                (updater, "updater-rc\n"),
            ):
                path.write_text(text)
            pleb.mkdir()
            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = "itsmygithubacct"
            env["GIT_AUTHOR_EMAIL"] = "itsmygithubacct@users.noreply.github.com"
            env["GIT_COMMITTER_NAME"] = env["GIT_AUTHOR_NAME"]
            env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
            subprocess.run(["git", "init", str(pleb)], check=True, capture_output=True)
            (pleb / "README").write_text("rc\n")
            subprocess.run(["git", "-C", str(pleb), "add", "README"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(pleb), "commit", "-m", "rc"],
                check=True, capture_output=True, env=env,
            )
            rc_head = subprocess.check_output(
                ["git", "-C", str(pleb), "rev-parse", "HEAD"], text=True,
            ).strip()
            manifest = root / "pre-hop"
            lines = [
                f"fingerprint\t{session}\t{fingerprint(session)}",
                f"fingerprint\t{closure}\t{fingerprint(closure)}",
                f"fingerprint\t{selector}\t{fingerprint(selector)}",
                f"fingerprint\t{updater}\t{fingerprint(updater)}",
                f"head\t{pleb}\t{rc_head}",
            ]
            manifest.write_text("\n".join(lines) + "\n")
            intact = compare(manifest, "rollback")
            self.assertEqual(intact.returncode, 0, intact.stderr)
            session.write_text("session-final\n")
            selector.write_text("selector-final\n")
            updater.write_text("updater-final\n")
            (pleb / "README").write_text("final\n")
            subprocess.run(["git", "-C", str(pleb), "add", "README"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(pleb), "commit", "-m", "final"],
                check=True, capture_output=True, env=env,
            )
            partial = compare(manifest, "rollback")
            self.assertNotEqual(partial.returncode, 0)
            for path in (session, selector, updater, pleb):
                self.assertIn(f"rollback did not restore {path}", partial.stderr)
            self.assertNotIn(f"rollback did not restore {closure}", partial.stderr)
            post = root / "post-hop"
            post.write_text(
                f"head\t{pleb}\t" + subprocess.check_output(
                    ["git", "-C", str(pleb), "rev-parse", "HEAD"], text=True,
                ).strip() + "\n"
            )
            subprocess.run(
                ["git", "-C", str(pleb), "reset", "--hard", rc_head],
                check=True, capture_output=True,
            )
            restoring = compare(post, "restoring hop")
            self.assertNotEqual(restoring.returncode, 0)
            self.assertIn(f"restoring hop did not restore {pleb}", restoring.stderr)

    def test_fresh_rc9_image_identity_comes_from_build_info(self):
        helper = "\n".join(
            self._bash_function(RUNNER.read_text(), name)
            for name in ("closure_shell_value", "assert_fresh_iso_identity")
        )
        commit = "a" * 40
        rc_object = "b" * 40
        with tempfile.TemporaryDirectory() as td:
            build_info = Path(td) / "build-info.env"
            build_info.write_text(
                "PLEBIAN_OS_VERSION=0.2.3\n"
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                f"PLEBIAN_OS_COMMIT={commit}\n"
            )

            def check(path=build_info):
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nassert_fresh_iso_identity "$1" v0.2.3-rc9 "$2" "$3"',
                     "bash", str(path), commit, rc_object],
                    capture_output=True, text=True, check=False,
                )

            self.assertEqual(check().returncode, 0, check().stderr)
            build_info.write_text(build_info.read_text().replace(commit, "c" * 40))
            wrong = check()
            self.assertNotEqual(wrong.returncode, 0)
            self.assertIn("source build-info commit", wrong.stderr)

    def test_pre_hop_manifest_matches_show_and_refuses_a_stale_neuronte(self):
        helper = "\n".join(
            self._bash_function(RUNNER.read_text(), name)
            for name in (
                "closure_shell_value", "show_resolved_value",
                "release_manifest_keys", "assert_pre_hop_manifest",
            )
        )
        commit = "a" * 40
        neuronte = "b" * 40
        pleb = "c" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            closure = root / "closure.env"
            manifest = root / "manifest.env"
            show = root / "show-before.txt"
            closure.write_text(
                f"PLEBIAN_OS_REF={commit}\nPLEB_REF={pleb}\n"
                f"NEURONTE_REF={neuronte}\nNEURONTE_REPO=https://example.invalid/neuronte.git\n"
            )
            manifest.write_text(
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                f"PLEB_REF={pleb}\nNEURONTE_REF={neuronte}\n"
                "NEURONTE_REPO=https://example.invalid/neuronte.git\n"
            )
            show.write_text(
                f"  PLEBIAN_OS_REF={commit}  [/etc/pleb/closure.env]\n"
                f"  PLEB_REF={pleb}  [/etc/pleb/closure.env]\n"
                f"  NEURONTE_REF={neuronte}  [/etc/pleb/closure.env]\n"
                "  NEURONTE_REPO=https://example.invalid/neuronte.git  [/etc/pleb/closure.env]\n"
            )

            def check():
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nassert_pre_hop_manifest "$1" "$2" "$3" v0.2.3-rc9 "$4"',
                     "bash", str(closure), str(show), str(manifest), commit],
                    capture_output=True, text=True, check=False,
                )

            self.assertEqual(check().returncode, 0, check().stderr)
            closure.write_text(closure.read_text().replace(neuronte, "d" * 40))
            stale = check()
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("NEURONTE_REF", stale.stderr)
            closure.write_text(closure.read_text().replace("d" * 40, neuronte))
            show.write_text(show.read_text().replace(pleb, "e" * 40))
            drifted = check()
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("PLEB_REF", drifted.stderr)
            show.write_text(show.read_text().replace("e" * 40, pleb))
            show.write_text(show.read_text().replace(commit, "f" * 40, 1))
            show_ref = check()
            self.assertNotEqual(show_ref.returncode, 0)
            self.assertIn("show-before PLEBIAN_OS_REF", show_ref.stderr)
            closure.write_text(
                closure.read_text() + f"NEURONTE_REF={'9' * 40}\n"
            )
            manifest.write_text(
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                f"PLEB_REF={pleb}\n"
                "NEURONTE_REPO=https://example.invalid/neuronte.git\n"
            )
            show.write_text(
                f"  PLEBIAN_OS_REF={commit}  [/etc/pleb/closure.env]\n"
                f"  PLEB_REF={pleb}  [/etc/pleb/closure.env]\n"
                f"  NEURONTE_REF={'9' * 40}  [/etc/pleb/closure.env]\n"
                "  NEURONTE_REPO=https://example.invalid/neuronte.git  [/etc/pleb/closure.env]\n"
            )
            omitted = check()
            self.assertNotEqual(omitted.returncode, 0)
            self.assertIn("NEURONTE_REF", omitted.stderr)

    def test_fresh_iso_show_resolves_the_commit_not_the_tag(self):
        helper = "\n".join(
            self._bash_function(RUNNER.read_text(), name)
            for name in (
                "closure_shell_value", "show_resolved_value",
                "release_manifest_keys", "assert_pre_hop_manifest",
            )
        )
        commit = "3199b8ec564b119073a8b08d3c312539ec0e38eb"
        pleb = "57683ebf8ac88ccbf7f160c4f7c6e0cc25936488"
        neuronte = "4134bf909594cf5c774f49677405fd1e22c4e2e4"
        repo = "https://github.com/itsmygithubacct/neuronte.git"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_info = root / "build-info.env"
            manifest = root / "manifest.env"
            show = root / "show-before.txt"
            build_info.write_text(
                "PLEBIAN_OS_VERSION=0.2.3\n"
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                f"PLEBIAN_OS_COMMIT={commit}\n"
                f"PLEB_REF={pleb}\n"
                f"NEURONTE_REF={neuronte}\n"
                f"NEURONTE_REPO={repo}\n"
            )
            manifest.write_text(
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                f"PLEB_REF={pleb}\n"
                f"NEURONTE_REF={neuronte}\n"
                f"NEURONTE_REPO={repo}\n"
            )
            show.write_text(
                f"  PLEBIAN_OS_REF={commit}  [/etc/pleb/session.env]\n"
                f"  PLEB_REF={pleb}  [/etc/pleb/session.env]\n"
                f"  NEURONTE_REF={neuronte}  [/etc/pleb/session.env]\n"
                f"  NEURONTE_REPO={repo}  [/etc/pleb/session.env]\n"
            )

            def check(show_path=show):
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nassert_pre_hop_manifest "$1" "$2" "$3" v0.2.3-rc9 "$4"',
                     "bash", str(build_info), str(show_path), str(manifest), commit],
                    capture_output=True, text=True, check=False,
                )

            fresh = check()
            self.assertEqual(fresh.returncode, 0, fresh.stderr)
            tagged = root / "show-tag.txt"
            tagged.write_text(show.read_text().replace(commit, "v0.2.3-rc9", 1))
            wrong = check(tagged)
            self.assertNotEqual(wrong.returncode, 0)
            self.assertIn("show-before PLEBIAN_OS_REF", wrong.stderr)

    def test_iso_recorded_tag_and_object_are_required(self):
        helper = self._bash_function(HOST_RUNNER.read_text(), "source_iso_names_installed_rc")
        good = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            info = Path(td) / "build-info.env"

            def check(text, tag="v0.2.3-rc9"):
                info.write_text(text)
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nsource_iso_names_installed_rc "$1" "$2"',
                     "bash", str(info), tag],
                    capture_output=True, text=True, check=False,
                )

            matched = check(
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                "PLEBIAN_OS_RELEASE_TAG=v0.2.3-rc9\n"
                f"PLEBIAN_OS_RELEASE_TAG_OBJECT={good}\n"
            )
            self.assertEqual(matched.returncode, 0, matched.stderr)
            self.assertEqual(matched.stdout.strip(), good)
            wrong_tag = check(
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                "PLEBIAN_OS_RELEASE_TAG=v0.2.3-rc8\n"
                f"PLEBIAN_OS_RELEASE_TAG_OBJECT={good}\n"
            )
            self.assertNotEqual(wrong_tag.returncode, 0)
            bare_object = check(
                "PLEBIAN_OS_REF=v0.2.3-rc9\n"
                "PLEBIAN_OS_RELEASE_TAG=v0.2.3-rc9\n"
                "PLEBIAN_OS_RELEASE_TAG_OBJECT=not-a-sha\n"
            )
            self.assertNotEqual(bare_object.returncode, 0)

    def test_release_manifest_is_bound_to_source_checksums(self):
        helper = self._bash_function(HOST_RUNNER.read_text(), "published_named_sha256")
        manifest_hash = "c4d7d269" + "a" * 56
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sums = root / "SHA256SUMS"
            manifest = root / "plebian-os-0.2.3-rc9.env"
            manifest.write_text("PLEBIAN_OS_REF=v0.2.3-rc9\n")
            actual = subprocess.check_output(["sha256sum", str(manifest)], text=True).split()[0]
            sums.write_text(
                f"{manifest_hash}  plebian-os-0.2.3-rc9.env\n"
                f"{'b' * 64}  plebian-os-0.2.3-rc9-amd64.iso\n"
            )
            listed = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\npublished_named_sha256 "$1" "$2"',
                 "bash", str(sums), manifest.name],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(listed.stdout.strip(), manifest_hash)
            self.assertNotEqual(actual, manifest_hash)
            sums.write_text(
                f"{manifest_hash}  plebian-os-0.2.3-rc9.env\n"
                f"{'d' * 64}  plebian-os-0.2.3-rc9.env\n"
            )
            doubled = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", helper +
                 '\npublished_named_sha256 "$1" "$2"',
                 "bash", str(sums), manifest.name],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(doubled.returncode, 0)

    def test_manifest_hash_comparison_uses_the_checksum_file(self):
        source = HOST_RUNNER.read_text()
        start = source.index('    manifest_sha256="$(published_named_sha256')
        end = source.index("release manifest checksum mismatch:", start)
        snippet = source[start:source.index("\n", end) + 1]
        self.assertIn('[ "$actual_manifest_sha256" = "$manifest_sha256" ]', snippet)
        self.assertIn(
            'die "source checksum file must name the release manifest exactly once"',
            snippet,
        )
        lookup = self._bash_function(source, "published_named_sha256")
        script = (
            'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
            + lookup
            + "\nsource_sha256sums=$1\nfrom_release_manifest=$2\n"
            + snippet
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "plebian-os-0.2.3-rc9.env"
            manifest.write_text("PLEBIAN_OS_REF=v0.2.3-rc9\n")
            actual = subprocess.check_output(
                ["sha256sum", str(manifest)], text=True).split()[0]
            sums = root / "SHA256SUMS"

            def check(text):
                sums.write_text(text)
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", script,
                     "bash", str(sums), str(manifest)],
                    capture_output=True, text=True, check=False,
                )

            bound = check(f"{actual}  plebian-os-0.2.3-rc9.env\n")
            self.assertEqual(bound.returncode, 0, bound.stderr)
            mismatched = check(f"{'ab' * 32}  plebian-os-0.2.3-rc9.env\n")
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertIn("release manifest checksum mismatch", mismatched.stderr)
            omitted = check(f"{actual}  plebian-os-0.2.3-rc9-amd64.iso\n")
            self.assertNotEqual(omitted.returncode, 0)
            self.assertIn("exactly once", omitted.stderr)

    def test_snapshot_engine_entry_rejects_a_different_generation(self):
        helper = self._bash_function(RUNNER.read_text(), "assert_release_snapshot_restored")
        live = hashlib.sha256(b"live-engine\n").hexdigest()
        other = hashlib.sha256(b"other-engine\n").hexdigest()
        script = (
            'bound_engine_fingerprint() { printf "%s\\n" live-engine; }\n'
            + helper
            + '\nassert_release_snapshot_restored rollback "$1"\n'
        )
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "snapshot"

            def check(expected):
                manifest.write_text(f"engine\t/engine/build\t{expected}\n")
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", script, "bash", str(manifest)],
                    capture_output=True, text=True, check=False,
                )

            same = check(live)
            self.assertEqual(same.returncode, 0, same.stderr)
            drifted = check(other)
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("did not restore", drifted.stderr)

    def test_recovery_meta_selection_tag_must_match_when_present(self):
        helper = self._bash_function(RUNNER.read_text(), "assert_recorded_selection_tag")
        expected = "532d238f65c4bc1dc82a817bab01a467e287ba16"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def check():
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", helper +
                     '\nassert_recorded_selection_tag "$1" "$2"',
                     "bash", str(root), expected],
                    capture_output=True, text=True, check=False,
                )

            absent = check()
            self.assertEqual(absent.returncode, 0, absent.stderr)
            self.assertEqual(absent.stdout.strip(), "absent")
            record = root / "closure-rollback.20261113T000000Z.abcd" 
            record.mkdir()
            (record / "meta").write_text(f"from=0.2.2\nto=0.2.3\nselection_tag={expected}\n")
            matched = check()
            self.assertEqual(matched.returncode, 0, matched.stderr)
            self.assertEqual(matched.stdout.strip(), "matched")
            (record / "meta").write_text("selection_tag=" + "f" * 40 + "\n")
            forged = check()
            self.assertNotEqual(forged.returncode, 0)
            self.assertIn("selection_tag", forged.stderr)
            record.chmod(0)
            try:
                hidden = check()
            finally:
                record.chmod(0o700)
            self.assertEqual(hidden.returncode, 0, hidden.stderr)
            self.assertEqual(hidden.stdout.strip(), "unreadable")

    def test_selection_tag_sudo_read_and_unreadable_are_distinct(self):
        source = RUNNER.read_text()
        helper = "\n".join(
            self._bash_function(source, name)
            for name in (
                "die", "record_check", "must",
                "assert_recorded_selection_tag", "record_selection_tag_check",
            )
        )
        expected = "532d238f65c4bc1dc82a817bab01a467e287ba16"
        wrong = "f" * 40
        script = helper + """
check_total=0
check_pass=0
report=$1
root=$2
expected=$3
checks=$report/checks.tsv
: >"$checks"
set +e
state=$(assert_recorded_selection_tag "$root" "$expected" 2>"$report/selection.stderr")
rc=$?
set -e
printf '%s\\n' "$rc"
printf '%s\\n' "$state"
if [ "$rc" -ne 0 ]; then
    cat "$report/selection.stderr" >&2
    exit "$rc"
fi
record_selection_tag_check "$state"
printf '%s\\n' "$check_pass/$check_total"
cat "$checks"
"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "report"
            report.mkdir()
            recovery = root / "recovery"
            recovery.mkdir()
            record = recovery / "closure-rollback.seat"
            record.mkdir()
            meta = record / "meta"
            readable = root / "readable-meta"
            bindir = root / "bin"
            bindir.mkdir()
            sudo_bin = bindir / "sudo"
            sudo_bin.write_text(
                "#!/bin/sh\n"
                '[ "$1" = "-n" ] || exit 1\n'
                "shift\n"
                'if [ "${SUDO_MODE:-fail}" = fail ]; then exit 1; fi\n'
                'if [ "$1" = test ]; then exit 0; fi\n'
                'if [ "$1" = cat ]; then cat -- "$SELECTION_TAG_META"; exit $?; fi\n'
                "exit 1\n"
            )
            sudo_bin.chmod(0o755)
            base_env = dict(os.environ)
            base_env["PATH"] = f"{bindir}:{base_env['PATH']}"
            base_env["SELECTION_TAG_META"] = str(readable)

            def run(mode):
                env = dict(base_env)
                env["SUDO_MODE"] = mode
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", script,
                     "bash", str(report), str(recovery), expected],
                    capture_output=True, text=True, check=False, env=env,
                )

            meta.write_text(f"selection_tag={expected}\n")
            readable.write_text(meta.read_text())
            direct = run("fail")
            self.assertEqual(direct.returncode, 0, direct.stderr)
            self.assertEqual(direct.stdout.splitlines()[0], "0")
            self.assertEqual(direct.stdout.splitlines()[1], "matched")
            self.assertIn("\tpass\t", direct.stdout)

            meta.write_text(f"selection_tag={wrong}\n")
            readable.write_text(meta.read_text())
            record.chmod(0)
            try:
                forged = run("read")
                hidden = run("fail")
            finally:
                record.chmod(0o700)
            self.assertNotEqual(forged.returncode, 0)
            self.assertIn("selection_tag", forged.stderr)
            self.assertEqual(hidden.returncode, 0, hidden.stderr)
            self.assertEqual(hidden.stdout.splitlines()[:3], ["0", "unreadable", "0/1"])
            self.assertIn(
                "recovery-meta-selection-tag-matches-published-rc-object\tnot-verified\tunreadable",
                hidden.stdout,
            )
            self.assertNotIn("\tpass\t", hidden.stdout)


if __name__ == "__main__":
    unittest.main()
