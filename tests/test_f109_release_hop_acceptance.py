"""Static and refusal controls for F109's operator-run VM qualification lane."""

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "build" / "acceptance-release-hop.sh"
HOST_RUNNER = ROOT / "build" / "acceptance-release-hop-host.sh"
RELEASING = ROOT / "RELEASING.md"


class F109ReleaseHopAcceptanceRunnerTests(unittest.TestCase):
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
