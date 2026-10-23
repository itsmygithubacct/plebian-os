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
        for token in (
            "--shape image|standalone",
            'case "$shape" in image|standalone)',
            '"$pleb_bin" update --to "$target" --yes --no-restart',
            '"$pleb_bin" update --to "$target" --dry-run --yes --no-restart',
            "PLEBIAN_OS_SELECT_TEST_FAIL_AFTER",
            "home-before.tsv",
            "home-after-failure.tsv",
            "home-after-success.tsv",
            "MANIFEST.sha256",
            'test ! -e /etc/pleb/session.env',
            'test ! -e "$source_home/plebian-os"',
            'test ! -e /usr/local/bin/plebian-os-update',
            '"installed-pleb-entrypoint-is-tested"',
            '"entrypoint-matches-participating-pleb-checkout"',
            '"starting-release-is-exact"',
            '"starting-pleb-ref-is-exact"',
            '"starting-kilix-ref-is-exact"',
            '"installed-$component-ref-matches-target"',
            '"image-build-info-matches-published-fixture"',
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
        self.assertEqual(text.count("acceptance-release-hop-host.sh"), 1)
        self.assertIn("--from <previous-x.y.z> --target <x.y.z>", text)
        self.assertIn("requires 2/2 distinct VM machine", text)
        self.assertIn("both 2/2 guest evidence sets", text)


if __name__ == "__main__":
    unittest.main()
