import ast
import hashlib
import io
import json
import os
import re
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_vm_image as vm


def args(**overrides):
    values = dict(
        yes=True, name=None, username="operator", fullname=None, password=None,
        password_file=None, password_hash_file=None,
        generate_one_time_password=True,
        expire_credential_after_verification=False,
        hostname="test-host", ram=None, cpus=None, vram=None, accelerate_3d=False,
        firmware=None,
        disk=None, session=None, kiosk=None, nopasswd_sudo=True, port=None,
        gui=False, no_wait=False, iso=None, no_verify=False,
        target="virtualbox",
        interactive_installer=False,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def cfg(**overrides):
    values = dict(
        name="test", username="pleb", fullname="Plebian User",
        password="strong-secret", hostname="plebian", ram_mb=1024, cpus=1,
        vram_mb=128, accelerate_3d=False, firmware="bios", disk_gb=8, desktop=True,
        kiosk=True, nopasswd_sudo=False, ssh_port=2222, gui=False, wait=False,
    )
    values.update(overrides)
    return vm.Config(**values)


class SourceProvenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "versions.env"

    def write_provenance(self, values):
        arguments = [item for pair in values.items() for item in pair]
        result = subprocess.run([
            "bash", "-c",
            'while [ "$#" -gt 0 ]; do printf "%s=%q\\n" "$1" "$2"; shift 2; done',
            "bash", *arguments,
        ], text=True, capture_output=True, check=True)
        self.path.write_text(result.stdout)

    def verify(self, expected):
        command = vm.source_provenance_command(expected, str(self.path))
        return subprocess.run(["bash", "-c", command], text=True, capture_output=True)

    def test_empty_and_quoted_records_match_without_executing_data(self):
        sentinel = self.root / "must-not-exist"
        values = {
            "KILIX_SYSTEM_MONITOR_BRANCH": "",
            "PLEBIAN_OS_COMMIT": "a" * 40,
            "QUOTED": "spaces, quote' and newline\n",
            "LITERAL": f"$(touch {shlex.quote(str(sentinel))})",
        }
        self.write_provenance(values)
        self.assertIn("KILIX_SYSTEM_MONITOR_BRANCH=''\n", self.path.read_text())
        result = self.verify(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(sentinel.exists())

    def test_each_mismatched_record_refuses(self):
        values = {"EMPTY": "", "COMMIT": "b" * 40, "ORDINARY": "selected"}
        self.write_provenance(values)
        for key in values:
            with self.subTest(key=key):
                self.assertNotEqual(self.verify({**values, key: "different"}).returncode, 0)

    def test_missing_and_noncanonical_empty_records_refuse(self):
        for payload in ("UNRELATED=value\n", "EMPTY=\n"):
            with self.subTest(payload=payload):
                self.path.write_text(payload)
                self.assertNotEqual(self.verify({"EMPTY": ""}).returncode, 0)


class InstalledOllamaDocumentationTests(unittest.TestCase):
    def test_public_build_closure_is_published_and_acceptance_checks_it(self):
        installer_path = ROOT / "provision" / "plebian-os-install-kilix-ollama-runtime"
        namespace = runpy.run_path(str(installer_path))
        installer = namespace["sync_public_notices"].__globals__
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generation = root / "generation"
            source_doc = generation / "usr/share/doc/ollama-runtime"
            source_notices = source_doc / "notices"
            source_notices.mkdir(parents=True)
            closure_payload = b"fixture build closure\n"
            (source_doc / "BUILD-CLOSURE").write_bytes(closure_payload)
            notice_payload = b"fixture notice\n"
            (source_notices / "license.txt").write_bytes(notice_payload)
            manifest_payload = (
                f"{hashlib.sha256(notice_payload).hexdigest()}  ./license.txt\n"
            ).encode("ascii")
            (source_notices / "SHA256SUMS").write_bytes(manifest_payload)

            public_doc = root / "public" / "ollama-runtime"
            public_notices = public_doc / "notices"
            public_closure = public_doc / "BUILD-CLOSURE"
            public_disposition = public_doc / "RELEASE-DISPOSITION"
            real_digest_file = installer["digest_file"]

            def fixture_digest_file(path, **kwargs):
                if kwargs.get("expected_owner") == 0:
                    kwargs["expected_owner"] = os.geteuid()
                return real_digest_file(path, **kwargs)

            def fixture_ensure_root_path(path, *, final_mode):
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(final_mode)

            def fixture_require_root_directory(path, *, private=False):
                info = path.lstat()
                if path.is_symlink() or not path.is_dir():
                    installer["fail"](f"not a real directory: {path}")
                if private and info.st_mode & 0o077:
                    installer["fail"](f"directory is not private: {path}")

            test_values = {
                "GENERATION": generation,
                "PUBLIC_DOC_ROOT": public_doc,
                "PUBLIC_NOTICE_ROOT": public_notices,
                "PUBLIC_BUILD_CLOSURE": public_closure,
                "PUBLIC_RELEASE_DISPOSITION": public_disposition,
                "NOTICE_RECORDS": 1,
                "NOTICE_MANIFEST_SIZE": len(manifest_payload),
                "NOTICE_MANIFEST_SHA256": hashlib.sha256(manifest_payload).hexdigest(),
                "BUILD_CLOSURE_SIZE": len(closure_payload),
                "BUILD_CLOSURE_SHA256": hashlib.sha256(closure_payload).hexdigest(),
            }
            with mock.patch.dict(installer, test_values), \
                    mock.patch.dict(installer, {
                        "digest_file": fixture_digest_file,
                        "ensure_root_path": fixture_ensure_root_path,
                        "require_root_directory": fixture_require_root_directory,
                    }):
                self.assertTrue(installer["sync_public_notices"](repair=True))
                self.assertEqual(public_closure.read_bytes(), closure_payload)
                self.assertEqual(public_closure.stat().st_mode & 0o777, 0o644)

                result = SimpleNamespace(returncode=0, stdout="", stderr="")
                with mock.patch.dict(os.environ, {}, clear=True), \
                        mock.patch.object(vm, "ssh", return_value=result) as remote, \
                        mock.patch.object(vm, "info"):
                    vm.verify_provisioning(cfg(), "askpass")
                    commands = [call.args[1] for call in remote.call_args_list]
                predicate = next(
                    command for command in commands
                    if "sha256sum --check --status SHA256SUMS" in command
                )
                predicate = predicate.replace(
                    "/usr/share/doc/ollama-runtime", str(public_doc)
                )
                accepted = subprocess.run(
                    ["/bin/bash", "-c", predicate],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(accepted.returncode, 0, accepted.stderr)

                before = public_closure.stat()
                self.assertFalse(installer["sync_public_notices"](repair=True))
                after = public_closure.stat()
                self.assertEqual((after.st_ino, after.st_mtime_ns),
                                 (before.st_ino, before.st_mtime_ns))

                public_closure.unlink()
                with self.assertRaises(installer["InstallFailure"]):
                    installer["sync_public_notices"](repair=False)
                self.assertTrue(installer["sync_public_notices"](repair=True))
                self.assertEqual(public_closure.read_bytes(), closure_payload)

                public_closure.write_bytes(b"wrong closure\n")
                public_closure.chmod(0o644)
                with self.assertRaises(installer["InstallFailure"]):
                    installer["sync_public_notices"](repair=False)
                with self.assertRaises(installer["InstallFailure"]):
                    installer["sync_public_notices"](repair=True)


class OllamaReleaseDispositionTests(unittest.TestCase):
    """RELEASE-DISPOSITION is published and checked exactly as BUILD-CLOSURE is."""

    INSTALLER = ROOT / "provision" / "plebian-os-install-kilix-ollama-runtime"
    SOURCE = ROOT / "provision" / "ollama" / "RELEASE-DISPOSITION"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        namespace = runpy.run_path(str(self.INSTALLER))
        self.installer = namespace["sync_public_notices"].__globals__
        generation = root / "generation"
        source_doc = generation / "usr/share/doc/ollama-runtime"
        source_notices = source_doc / "notices"
        source_notices.mkdir(parents=True)
        closure_payload = b"fixture build closure\n"
        (source_doc / "BUILD-CLOSURE").write_bytes(closure_payload)
        notice_payload = b"fixture notice\n"
        (source_notices / "license.txt").write_bytes(notice_payload)
        manifest_payload = (
            f"{hashlib.sha256(notice_payload).hexdigest()}  ./license.txt\n"
        ).encode("ascii")
        (source_notices / "SHA256SUMS").write_bytes(manifest_payload)
        self.public_doc = root / "public" / "ollama-runtime"
        self.disposition = self.public_doc / "RELEASE-DISPOSITION"
        self.digest_calls = []
        real_digest_file = self.installer["digest_file"]

        def fixture_digest_file(path, **kwargs):
            self.digest_calls.append((Path(path), dict(kwargs)))
            if kwargs.get("expected_owner") == 0:
                kwargs["expected_owner"] = os.geteuid()
            return real_digest_file(path, **kwargs)

        def fixture_ensure_root_path(path, *, final_mode):
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(final_mode)

        def fixture_require_root_directory(path, *, private=False):
            if path.is_symlink() or not path.is_dir():
                self.installer["fail"](f"not a real directory: {path}")

        patcher = mock.patch.dict(self.installer, {
            "GENERATION": generation,
            "PUBLIC_DOC_ROOT": self.public_doc,
            "PUBLIC_NOTICE_ROOT": self.public_doc / "notices",
            "PUBLIC_BUILD_CLOSURE": self.public_doc / "BUILD-CLOSURE",
            "PUBLIC_RELEASE_DISPOSITION": self.disposition,
            "NOTICE_RECORDS": 1,
            "NOTICE_MANIFEST_SIZE": len(manifest_payload),
            "NOTICE_MANIFEST_SHA256": hashlib.sha256(manifest_payload).hexdigest(),
            "BUILD_CLOSURE_SIZE": len(closure_payload),
            "BUILD_CLOSURE_SHA256": hashlib.sha256(closure_payload).hexdigest(),
            "digest_file": fixture_digest_file,
            "ensure_root_path": fixture_ensure_root_path,
            "require_root_directory": fixture_require_root_directory,
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.expected = self.SOURCE.read_bytes()

    def sync(self, *, repair):
        return self.installer["sync_public_notices"](repair=repair)

    def test_exact_bytes_mode_and_root_owner_are_published(self):
        self.assertTrue(self.sync(repair=True))
        self.assertEqual(self.disposition.read_bytes(), self.expected)
        self.assertEqual(self.disposition.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.disposition.stat().st_uid, os.geteuid())
        # The fixture only maps root to the test user; the installer itself
        # must demand root ownership, mode 0644 and the pinned size and hash.
        requests = [
            kwargs for path, kwargs in self.digest_calls if path == self.disposition
        ]
        self.assertTrue(requests)
        for kwargs in requests:
            self.assertEqual(kwargs["expected_size"], len(self.expected))
            self.assertEqual(
                kwargs["expected_hash"], hashlib.sha256(self.expected).hexdigest()
            )
            self.assertEqual(kwargs["expected_mode"], 0o644)
        self.assertIn(
            0, [kwargs["expected_owner"] for path, kwargs in self.digest_calls
                if path == self.disposition and "expected_owner" in kwargs]
        )
        before = self.disposition.stat()
        self.assertFalse(self.sync(repair=True))
        after = self.disposition.stat()
        self.assertEqual((after.st_ino, after.st_mtime_ns),
                         (before.st_ino, before.st_mtime_ns))
        self.assertFalse(self.sync(repair=False))

    def test_missing_file_is_refused_when_verifying_and_repaired_otherwise(self):
        self.assertTrue(self.sync(repair=True))
        self.disposition.unlink()
        with self.assertRaises(self.installer["InstallFailure"]):
            self.sync(repair=False)
        self.assertFalse(self.disposition.exists())
        self.assertTrue(self.sync(repair=True))
        self.assertEqual(self.disposition.read_bytes(), self.expected)

    def test_planted_size_hash_or_mode_mismatch_is_refused_not_replaced(self):
        self.assertTrue(self.sync(repair=True))
        flipped = bytes([self.expected[0] ^ 1]) + self.expected[1:]
        plants = {
            "size": (self.expected + b"extra\n", 0o644),
            "truncated": (self.expected[:-1], 0o644),
            "hash": (flipped, 0o644),
            "mode 0600": (self.expected, 0o600),
            "mode 0664": (self.expected, 0o664),
            "mode 0755": (self.expected, 0o755),
        }
        for label, (payload, mode) in plants.items():
            for repair in (False, True):
                with self.subTest(plant=label, repair=repair):
                    self.disposition.write_bytes(payload)
                    self.disposition.chmod(mode)
                    with self.assertRaises(self.installer["InstallFailure"]):
                        self.sync(repair=repair)
                    self.assertEqual(self.disposition.read_bytes(), payload)
                    self.assertEqual(self.disposition.stat().st_mode & 0o777, mode)

    def test_preexisting_different_file_is_refused_like_build_closure(self):
        self.assertTrue(self.sync(repair=True))
        closure = self.public_doc / "BUILD-CLOSURE"
        for target in (closure, self.disposition):
            with self.subTest(target=target.name):
                good = target.read_bytes()
                target.write_bytes(b"operator wrote this\n")
                target.chmod(0o644)
                for repair in (False, True):
                    with self.assertRaises(self.installer["InstallFailure"]):
                        self.sync(repair=repair)
                    self.assertEqual(target.read_bytes(), b"operator wrote this\n")
                target.write_bytes(good)

    def test_symlink_in_place_of_the_file_is_refused(self):
        self.assertTrue(self.sync(repair=True))
        good = self.disposition.read_bytes()
        elsewhere = self.public_doc.parent / "elsewhere"
        elsewhere.write_bytes(good)
        elsewhere.chmod(0o644)
        self.disposition.unlink()
        self.disposition.symlink_to(elsewhere)
        for repair in (False, True):
            with self.assertRaises(self.installer["InstallFailure"]):
                self.sync(repair=repair)
        self.assertTrue(self.disposition.is_symlink())

    def test_embedded_bytes_pin_and_source_file_agree(self):
        source = self.SOURCE.read_bytes()
        self.assertEqual(
            self.installer["RELEASE_DISPOSITION_SOURCE"].encode("ascii"), source
        )
        self.assertEqual(self.installer["RELEASE_DISPOSITION_SIZE"], len(source))
        self.assertEqual(
            self.installer["RELEASE_DISPOSITION_SHA256"],
            hashlib.sha256(source).hexdigest(),
        )
        self.assertEqual(vm.pinned_release_disposition(),
                         (len(source), hashlib.sha256(source).hexdigest()))
        pristine = runpy.run_path(str(self.INSTALLER))
        self.assertEqual(
            pristine["PUBLIC_RELEASE_DISPOSITION"],
            Path("/usr/share/doc/ollama-runtime/RELEASE-DISPOSITION"),
        )

    def acceptance_command(self):
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_provisioning(cfg(), "askpass")
            commands = [call.args[1] for call in remote.call_args_list]
        return next(
            command for command in commands
            if "sha256sum --check --status SHA256SUMS" in command
        )

    def run_acceptance(self, doc):
        predicate = self.acceptance_command().replace(
            "/usr/share/doc/ollama-runtime", str(doc)
        )
        return subprocess.run(
            ["/bin/bash", "-c", predicate],
            text=True, capture_output=True, check=False,
        )

    def acceptance_tree(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        doc = Path(temporary.name) / "ollama-runtime"
        (doc / "notices").mkdir(parents=True)
        (doc / "BUILD-CLOSURE").write_bytes(b"fixture build closure\n")
        notice = b"fixture notice\n"
        (doc / "notices" / "license.txt").write_bytes(notice)
        (doc / "notices" / "SHA256SUMS").write_text(
            f"{hashlib.sha256(notice).hexdigest()}  ./license.txt\n"
        )
        return doc

    def test_acceptance_check_requires_the_pinned_release_disposition(self):
        doc = self.acceptance_tree()
        target = doc / "RELEASE-DISPOSITION"
        self.assertNotEqual(self.run_acceptance(doc).returncode, 0, "missing file")
        target.write_bytes(self.expected)
        accepted = self.run_acceptance(doc)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        flipped = bytes([self.expected[0] ^ 1]) + self.expected[1:]
        for label, payload in {
            "altered same size": flipped,
            "extended": self.expected + b"\n",
            "truncated": self.expected[:-1],
            "empty": b"",
        }.items():
            with self.subTest(altered=label):
                target.write_bytes(payload)
                self.assertNotEqual(self.run_acceptance(doc).returncode, 0)
        target.unlink()
        elsewhere = doc.parent / "elsewhere"
        elsewhere.write_bytes(self.expected)
        target.symlink_to(elsewhere)
        self.assertNotEqual(self.run_acceptance(doc).returncode, 0, "symlink")
        target.unlink()
        target.write_bytes(self.expected)
        self.assertEqual(self.run_acceptance(doc).returncode, 0)
        (doc / "BUILD-CLOSURE").unlink()
        self.assertNotEqual(self.run_acceptance(doc).returncode, 0, "no closure")


class OllamaApiVersionPredicateTests(unittest.TestCase):
    def test_generated_predicate_accepts_only_installer_metadata_version(self):
        predicate = vm.ollama_api_version_predicate()
        expected_version = vm.pinned_ollama_version()
        self.assertIn(json.dumps(expected_version), predicate)
        self.assertIn("assert version == expected, (version, expected)", predicate)

        for fake_version, should_pass in (
            (expected_version, True),
            ("0.32.14", False),
            ("0.32.15", False),
        ):
            with self.subTest(version=fake_version):
                def open_fake(url, *, timeout):
                    self.assertEqual(url, "http://127.0.0.1:11434/api/version")
                    self.assertEqual(timeout, 5)
                    return io.BytesIO(json.dumps({"version": fake_version}).encode())

                fake_opener = SimpleNamespace(open=open_fake)
                with mock.patch(
                    "urllib.request.build_opener", return_value=fake_opener
                ):
                    if should_pass:
                        exec(predicate, {})
                    else:
                        with self.assertRaises(AssertionError):
                            exec(predicate, {})


@unittest.skipUnless(shutil.which("apt-get"), "apt source parsing is required")
class LiveSecuritySourceTests(unittest.TestCase):
    def verify(self, files, configuration=""):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            apt = root / "apt"
            (apt / "sources.list.d").mkdir(parents=True)
            (root / "apt.conf.d").mkdir()
            (root / "lists").mkdir()
            config = root / "apt.conf"
            config.write_text(
                f'Dir::Etc::main "{root}/unused";\n'
                f'Dir::Etc::parts "{root}/apt.conf.d";\n'
                f'Dir::State::lists "{root}/lists";\n'
                + configuration
            )
            for name, text in files.items():
                (apt / name).write_text(text)
            command = vm.live_debian_security_source_command(
                str(apt), str(ROOT / "provision" / "plebian-os-provision.sh"))
            return subprocess.run(
                ["bash", "-c", command], text=True, capture_output=True,
                env={**os.environ, "APT_CONFIG": str(config)}, check=False,
            )

    def test_stock_installer_sources_list_passes_with_both_transports(self):
        for scheme in ("http", "https"):
            with self.subTest(scheme=scheme):
                result = self.verify({"sources.list": (
                    f"deb {scheme}://deb.debian.org/debian trixie main contrib non-free non-free-firmware\n"
                    f"deb {scheme}://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware\n"
                    f"deb {scheme}://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n"
                )})
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_deb822_sources_accept_either_official_archive_and_transport(self):
        for host in ("deb.debian.org", "security.debian.org"):
            for scheme in ("http", "https"):
                with self.subTest(host=host, scheme=scheme):
                    result = self.verify({"sources.list.d/debian.sources": (
                        "# Existing Debian source, independent of Plebian filenames\n\n"
                        "Types: deb\n"
                        f"URIs: {scheme}://{host}/debian-security/\n"
                        "Suites: trixie-security\nComponents: main\n"
                        "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
                    )})
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_inactive_or_unrelated_sources_do_not_satisfy_security(self):
        valid = "deb http://security.debian.org/debian-security trixie-security main\n"
        cases = (
            {"sources.list": "# " + valid},
            {"sources.list.d/old.list.disabled": valid},
            {"sources.list.d/debian.sources": (
                "Types: deb\nURIs: https://security.debian.org/debian-security\n"
                "Suites: trixie-security\nComponents: main\nEnabled: no\n"
            )},
            {"sources.list": valid.replace("deb ", "deb-src ", 1)},
            {"sources.list": valid.replace("trixie-security", "trixie")},
            {"sources.list": valid.replace(" main", " contrib")},
            {"sources.list": valid.replace(
                "http://security.debian.org/debian-security",
                "http://snapshot.debian.org/archive/debian-security/20260727T000000Z")},
            {"sources.list": valid.replace("security.debian.org", "security.debian.org.example.invalid")},
        )
        for files in cases:
            with self.subTest(files=files):
                result = self.verify(files)
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_signature_and_replay_bypasses_refuse_in_both_formats(self):
        for option, value in (
            ("Trusted", "yes"), ("Allow-Insecure", "yes"),
            ("Allow-Weak", "yes"), ("Allow-Downgrade-To-Insecure", "yes"),
            ("Check-Valid-Until", "no"), ("Check-Date", "0"),
        ):
            for deb822 in (False, True):
                with self.subTest(option=option, deb822=deb822):
                    if deb822:
                        files = {"sources.list.d/debian.sources": (
                            "Types: deb\nURIs: http://security.debian.org/debian-security\n"
                            "Suites: trixie-security\nComponents: main\n"
                            f"{option}: {value}\n"
                        )}
                    else:
                        files = {"sources.list": (
                            f"deb [{option.lower()}={value}] http://security.debian.org/debian-security "
                            "trixie-security main\n"
                        )}
                    result = self.verify(files)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("disables signature or replay checks", result.stderr)

    def test_global_signature_bypasses_refuse_even_with_an_ordinary_source(self):
        files = {"sources.list": "deb http://security.debian.org/debian-security trixie-security main\n"}
        for key in (
            "APT::Get::AllowUnauthenticated", "Acquire::AllowInsecureRepositories",
            "Acquire::AllowWeakRepositories", "Acquire::AllowDowngradeToInsecureRepositories",
        ):
            with self.subTest(key=key):
                result = self.verify(files, f'{key} "true";\n')
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_explicit_secure_options_pass_and_inactive_bypasses_are_ignored(self):
        result = self.verify({"sources.list": (
            "# deb [trusted=yes] http://security.debian.org/debian-security trixie-security main\n"
            "deb [trusted=no check-valid-until=yes check-date=1] "
            "http://security.debian.org/debian-security trixie-security main\n"
        ), "sources.list.d/disabled.sources": (
            "Types: deb\nURIs: https://security.debian.org/debian-security\n"
            "Suites: trixie-security\nComponents: main\nEnabled: no\nTrusted: yes\n"
        )})
        self.assertEqual(result.returncode, 0, result.stderr)


class SelectedClosureGateTests(unittest.TestCase):
    """Exercise acceptance-generated options against real release selection."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.remote = self.root / "published"
        subprocess.run(["git", "init", "-q", str(self.remote)], check=True)
        subprocess.run([
            "git", "-C", str(self.remote), "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty",
            "-qm", "published release fixture",
        ], check=True)
        subprocess.run(["git", "-C", str(self.remote), "tag", "v0.2.1"], check=True)

    def select(self, options):
        environment = {
            "PATH": os.defpath, "HOME": str(self.root),
            "PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY": "1",
            "FIXTURE_PUBLISHED_REPO": str(self.remote),
            "PLEBIAN_OS_VERSION": "0.2.2",
        }
        return subprocess.run([
            "bash", "-c",
            'update_path=$1; shift; source "$update_path"; '
            'PLEBIAN_OS_REPO=$FIXTURE_PUBLISHED_REPO; '
            'select_latest_release_if_needed; '
            'printf "SELECTED:%s:%s\\n" "$PLEBIAN_OS_VERSION" "$restart_arg"',
            "bash", str(ROOT / "provision" / "plebian-os-update.sh"), *options,
        ], env=environment, text=True, capture_output=True)

    def generated_options(self, gate):
        success = SimpleNamespace(returncode=0, stdout="", stderr="")
        before = SimpleNamespace(returncode=0, stdout="fixture-invocation\n", stderr="")
        replies = [success] if gate == "rollback" else [before, success, success]
        with mock.patch.object(vm, "ssh", side_effect=replies) as remote, \
                mock.patch.object(vm, "info"), mock.patch.object(vm, "_RECORDER", None):
            if gate == "rollback":
                vm.verify_update_rollback(cfg(), "askpass")
            else:
                vm.verify_successful_update(cfg(), "askpass")
        commands = [call.args[1] for call in remote.call_args_list]
        pattern = r"\btimeout [0-9]+ /usr/local/bin/plebian-os-update((?: --[a-z-]+)*)"
        matches = [re.search(pattern, command) for command in commands]
        options = [shlex.split(match.group(1)) for match in matches if match]
        self.assertEqual(len(options), 1)
        return options[0]

    def test_rollback_reaches_the_unpublished_selected_closure(self):
        result = self.select(self.generated_options("rollback"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SELECTED:0.2.2:--no-restart", result.stdout)

    def test_successful_update_keeps_selected_closure_and_restart(self):
        result = self.select(self.generated_options("success"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SELECTED:0.2.2:--restart", result.stdout)

    def test_plain_update_still_refuses_an_implicit_downgrade(self):
        result = self.select([])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing an implicit downgrade", result.stderr)
        self.assertNotIn("SELECTED:", result.stdout)


class VmBuilderEnvTests(unittest.TestCase):
    def test_external_window_requires_graphical_qemu(self):
        for arguments in (["--target", "qemu"], ["--target", "virtualbox", "--gui"]):
            with self.subTest(arguments=arguments), \
                    mock.patch.object(sys, "argv", ["build_vm_image.py", "--dry-run",
                                                   "--external-window", *arguments]), \
                    mock.patch.object(vm, "qemu_create") as create:
                with self.assertRaises(SystemExit):
                    vm.main()
                create.assert_not_called()

    def test_qemu_gui_defaults_to_foreground_tab_but_external_is_explicit(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(vm.qemu_tab, "launch") as tab, \
                mock.patch.object(vm, "run") as invoke:
            directory = Path(td) / "VM with spaces"
            iso = Path(td) / "installer with spaces.iso"
            vm.qemu_start(cfg(gui=True), iso, directory)
            argv, title, selected = tab.call_args.args
            self.assertEqual(selected, directory)
            self.assertIn(f"file={iso},media=cdrom,readonly=on", argv)
            self.assertEqual(argv[argv.index("-display") + 1], "gtk")
            self.assertNotIn("-daemonize", argv)
            invoke.assert_not_called()
            tab.reset_mock()
            vm.qemu_start(cfg(gui=True, external_window=True), iso, directory)
            tab.assert_not_called()
            self.assertEqual(invoke.call_args.args[0], [*argv, "-daemonize"])

    def test_qemu_creates_private_sparse_disk_and_boots_installer_once(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(vm, "storage_dir", return_value=Path(td)), \
                mock.patch.object(vm, "run") as invoke:
            selected = cfg(name="rc5-qemu", disk_gb=20, ssh_port=32222)
            vm_dir = vm.qemu_create(selected)
            self.assertEqual(vm_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(invoke.call_args.args[0][:4],
                             ["qemu-img", "create", "-f", "qcow2"])
            vm.qemu_start(selected, Path("/tmp/installer.iso"), vm_dir)
            argv = invoke.call_args.args[0]
            self.assertIn("q35,accel=kvm", argv)
            self.assertIn("once=d,order=c", argv)
            self.assertIn("user,id=net0,hostfwd=tcp:127.0.0.1:32222-:22", argv)
            self.assertIn("none", argv)
            self.assertIn("-daemonize", argv)
            with self.assertRaises(SystemExit):
                vm.qemu_create(selected)

    def test_qemu_efi_uses_private_variables_and_readonly_code(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(vm, "storage_dir", return_value=Path(td)), \
                mock.patch.object(vm, "run") as invoke:
            code, variables = Path(td) / "code.fd", Path(td) / "vars.fd"
            code.write_bytes(b"firmware code")
            variables.write_bytes(b"initial variables")
            with mock.patch.object(vm, "qemu_firmware", return_value=(code, variables)):
                directory = vm.qemu_create(cfg(firmware="efi"))
            private = directory / "OVMF_VARS.fd"
            self.assertNotEqual(private.stat().st_ino, variables.stat().st_ino)
            private.write_bytes(b"guest variables")
            self.assertEqual(variables.read_bytes(), b"initial variables")
            self.assertEqual((directory / "OVMF_CODE.fd").stat().st_mode & 0o777, 0o400)
            vm.qemu_start(cfg(firmware="efi"), Path(td) / "image.iso", directory)
            argv = invoke.call_args.args[0]
            self.assertIn(f"if=pflash,format=raw,unit=0,readonly=on,file={directory / 'OVMF_CODE.fd'}", argv)
            self.assertIn(f"if=pflash,format=raw,unit=1,file={private}", argv)
            record = json.loads((directory / "firmware.json").read_text())
            self.assertEqual(record["OVMF_VARS.fd"]["sha256"],
                             hashlib.sha256(b"initial variables").hexdigest())

    def test_missing_efi_inputs_refuse_before_creating_vm_state(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(vm, "storage_dir", return_value=Path(td)), \
                mock.patch.dict(os.environ, {"PLEBIAN_OS_OVMF_CODE": str(Path(td) / "missing")}):
            with self.assertRaises(SystemExit):
                vm.qemu_create(cfg(firmware="efi"))
            self.assertFalse((Path(td) / "qemu-vms").exists())

    def test_qemu_report_records_hypervisor_and_target(self):
        git_results = [SimpleNamespace(stdout="a" * 40 + "\n"),
                       SimpleNamespace(stdout="")]
        with mock.patch.object(vm, "run", return_value=SimpleNamespace(
                stdout="QEMU emulator version 9.0.0\n")), \
                mock.patch.object(vm.subprocess, "run", side_effect=git_results):
            report = vm.acceptance_report_initial(cfg(), args(target="qemu"))
        self.assertEqual(report["vm"]["target"], "qemu")
        self.assertEqual(report["host"]["qemu_version"], "QEMU emulator version 9.0.0")

    def test_default_wait_budget_covers_install_and_firstboot(self):
        self.assertEqual(vm.DEFAULT_PROVISION_TIMEOUT_MINUTES, 120)
        result = subprocess.run(
            [sys.executable, str(ROOT / "build" / "build_vm_image.py"),
             "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "combined minutes to wait for Debian installation",
            result.stdout,
        )
        self.assertIn("firstboot (default: 120)", result.stdout)

    def test_automated_preseed_inserts_hashed_identity_into_clean_template(self):
        with mock.patch.object(vm, "crypt_password", return_value=("$6$hash", True)):
            text = vm.generate_preseed(cfg()).read_text()
        self.assertIn("d-i passwd/username string pleb", text)
        self.assertIn("d-i netcfg/get_hostname string plebian", text)
        self.assertIn("d-i netcfg/hostname string plebian\n", text)
        self.assertIn("d-i passwd/user-password-crypted password $6$hash", text)
        self.assertNotIn("d-i passwd/user-password password", text)
        self.assertNotIn("PLEB_REF=%s", text)
        self.assertNotIn("env_fmt", text)

    def test_selected_hostname_requires_persistent_and_runtime_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            persistent = root / "hostname file"
            runtime = root / "hostname"
            command = vm.guest_hostname_command("selected-host", str(persistent))
            for saved, active, exit_code, expected_ok in (
                ("selected-host", "selected-host", 0, True),
                ("dns-host", "selected-host", 0, False),
                ("selected-host", "dns-host", 0, False),
                ("dns-host", "dns-host", 0, False),
                ("", "selected-host", 0, False),
                ("selected-host", "", 1, False),
                ("selected-host", "selected-host", 1, False),
            ):
                with self.subTest(saved=saved, active=active, exit_code=exit_code):
                    persistent.write_text(saved + "\n")
                    runtime.write_text(
                        "#!/bin/sh\n" + f"printf '%s\\n' {shlex.quote(active)}\n"
                        + f"exit {exit_code}\n")
                    runtime.chmod(0o700)
                    result = subprocess.run(
                        ["/bin/sh", "-c", command], capture_output=True, text=True,
                        env={"PATH": str(root) + os.pathsep + os.defpath})
                    self.assertEqual(result.returncode == 0, expected_ok, result.stderr)
            persistent.unlink()
            self.assertNotEqual(subprocess.run(
                ["/bin/sh", "-c", command], capture_output=True,
                env={"PATH": str(root) + os.pathsep + os.defpath}).returncode, 0)

    def test_hostname_mismatch_fails_acceptance_before_update_or_catalog(self):
        command = vm.guest_hostname_command("selected-host")
        def remote(_cfg, actual, _askpass, **kwargs):
            return SimpleNamespace(returncode=int(actual == command), stdout="", stderr="")
        with mock.patch.dict(os.environ, {
                "PLEBIAN_OS_VERIFY_UPDATE_ROLLBACK": "1",
                "PLEBIAN_OS_VERIFY_SUCCESSFUL_UPDATE": "1",
                "PLEBIAN_OS_VERIFY_CATALOG_BUILDS": "1",
        }, clear=True), mock.patch.object(vm, "ssh", side_effect=remote), \
                mock.patch.object(vm, "info"), \
                mock.patch.object(vm, "verify_update_rollback") as rollback, \
                mock.patch.object(vm, "verify_successful_update") as update, \
                mock.patch.object(vm, "verify_catalog_builds") as catalog, \
                mock.patch.object(vm, "die", side_effect=SystemExit(1)) as fatal, \
                self.assertRaises(SystemExit):
            vm.verify_provisioning(cfg(hostname="selected-host"), "askpass")
        self.assertIn("selected hostname", fatal.call_args.args[0])
        rollback.assert_not_called()
        update.assert_not_called()
        catalog.assert_not_called()

    def test_build_iso_forwards_authoritative_runtime_config(self):
        seen = {}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.iso"
            seed = Path(td) / "preseed.cfg"
            seed.write_text("seed\n")

            def fake_run(_argv, **kwargs):
                seen.update(kwargs["env"])
                out.write_bytes(b"iso")

            with mock.patch.object(vm, "run", side_effect=fake_run):
                vm.build_iso(cfg(), seed, out, False)

        expected = vm.runtime_build_env(cfg())
        for key, value in expected.items():
            self.assertEqual(seen[key], value)
        self.assertEqual(seen["PLEBIAN_OS_SSH_ENABLED"], "1")
        self.assertEqual(seen["PLEBIAN_OS_AUTOBOOT"], "1")
        self.assertEqual(seen["PLEBIAN_OS_UNATTENDED_DISK"], "1")

    def test_build_iso_passes_the_ollama_carrier_as_remaster_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "out.iso"
            seed = root / "preseed.cfg"
            carrier = root / "ollama-carrier.tar.xz"
            seed.write_text("seed\n")
            carrier.write_bytes(b"carrier")

            def fake_run(_argv, **_kwargs):
                out.write_bytes(b"iso")

            with mock.patch.object(vm, "run", side_effect=fake_run) as run:
                vm.build_iso(cfg(), seed, out, False, ollama_carrier=carrier)

        self.assertEqual(
            run.call_args.args[0],
            [vm.REMASTER, "", str(out), str(carrier.resolve())],
        )

    def test_build_iso_defaults_the_carrier_from_the_shared_environment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "out.iso"
            seed = root / "preseed.cfg"
            carrier = root / "ollama carrier.tar.xz"
            seed.write_text("seed\n")

            def fake_run(_argv, **kwargs):
                out.write_bytes(b"iso")
                self.assertEqual(
                    kwargs["env"]["PLEBIAN_OS_OLLAMA_CARRIER"], str(carrier))

            with mock.patch.dict(os.environ, {
                    "PLEBIAN_OS_OLLAMA_CARRIER": str(carrier)}), \
                    mock.patch.object(vm, "run", side_effect=fake_run) as run:
                vm.build_iso(cfg(), seed, out, False)

        self.assertEqual(
            run.call_args.args[0],
            [vm.REMASTER, "", str(out), str(carrier)],
        )

    def test_acceptance_checks_coordinated_source_allocation(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        self.assertIn('"coordinated checkouts"', source)
        self.assertIn('"pleb recovery guide"', source)
        self.assertIn("/usr/local/share/doc/pleb/RECOVERY.md", source)
        for commit in (
            "PLEBIAN_OS_COMMIT", "PLEB_COMMIT", "KILIX_COMMIT",
            "KILIX95_COMMIT",
        ):
            self.assertIn(commit, source[source.index("def verify_provisioning"):])
        self.assertIn(
            're.fullmatch(r"[0-9a-fA-F]{40}"',
            source[source.index("def verify_provisioning"):],
        )
        for ref in ("PLEBIAN_OS_REF", "PLEB_REF", "KILIX_REF", "KILIX95_REF"):
            self.assertIn(ref, source[source.index("def verify_provisioning"):])
        self.assertIn('git -C "${dir_var}" rev-parse HEAD', source)
        self.assertIn('"provision version"', source)
        self.assertIn(
            "/usr/local/sbin/plebian-os-provision --version",
            source[source.index("def verify_provisioning"):],
        )
        self.assertIn('"component versions"', source)
        self.assertIn("/usr/local/bin/pleb --version", source)
        self.assertIn('"$KILIX_DIR/kilix" --kilix-version', source)
        self.assertIn('python3 "$KILIX95_DIR/main.py" --version', source)
        self.assertIn('"session exports"', source)
        self.assertIn('KILIX95_REF=', source[source.index("def verify_provisioning"):])
        for checkout in ("PLEBIAN_OS_DIR", "PLEB_DIR", "KILIX_DIR", "KILIX95_DIR"):
            self.assertIn(checkout, source[source.index("def verify_provisioning"):])

    def test_acceptance_checks_live_debian_security_contract(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        for name in ("live Debian security source", "apt validity checks enabled",
                     "security upgrades enabled"):
            self.assertIn(f'("{name}",', verify)
        self.assertIn('("live Debian security source", live_debian_security_source_command())', verify)
        self.assertIn("/etc/apt/apt.conf.d/52plebian-os-security-upgrades", verify)
        validity = next(
            node.elts[1].value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Tuple) and len(node.elts) == 2
            and all(isinstance(elt, ast.Constant) for elt in node.elts)
            and node.elts[0].value == "apt validity checks enabled"
        )
        cases = (
            ({}, 0),
            ({"FAKE_CHECK_VALID_UNTIL": "true", "FAKE_CHECK_DATE": "1"}, 0),
            ({"FAKE_CHECK_VALID_UNTIL": "false"}, 1),
            ({"FAKE_CHECK_VALID_UNTIL": "0x0"}, 1),
            ({"FAKE_CHECK_DATE": "No"}, 1),
            ({"FAKE_CHECK_DATE": "00"}, 1),
            # apt also reads a signed or space-padded zero as false.
            ({"FAKE_CHECK_DATE": "+0"}, 1),
            ({"FAKE_CHECK_DATE": "-0"}, 1),
            ({"FAKE_CHECK_DATE": " 0"}, 1),
            ({"FAKE_APT_CONFIG_RC": "100"}, 1),
        )
        with tempfile.TemporaryDirectory() as td:
            # The real apt-config answers from an isolated configuration that
            # holds only the FAKE_* keys, so apt itself reads each spelling and
            # nothing under this host's /etc/apt is consulted.
            real_config = shutil.which("apt-config") or "/usr/bin/apt-config"
            isolated = Path(td) / "apt.conf"
            parts = Path(td) / "apt.conf.d"
            parts.mkdir()
            config = Path(td) / "apt-config"
            config.write_text(
                "#!/bin/sh\n"
                '[ -z "${FAKE_APT_CONFIG_RC:-}" ] || exit "$FAKE_APT_CONFIG_RC"\n'
                "{\n"
                f"  printf 'Dir::Etc::main \"%s\";\\nDir::Etc::parts \"%s\";\\n' "
                f"{str(isolated) + '.none'!r} {str(parts)!r}\n"
                '  [ -z "${FAKE_CHECK_VALID_UNTIL:-}" ] '
                "|| printf 'Acquire::Check-Valid-Until \"%s\";\\n' \"$FAKE_CHECK_VALID_UNTIL\"\n"
                '  [ -z "${FAKE_CHECK_DATE:-}" ] '
                "|| printf 'Acquire::Check-Date \"%s\";\\n' \"$FAKE_CHECK_DATE\"\n"
                f"}} > {str(isolated)!r}\n"
                f"APT_CONFIG={str(isolated)!r} exec {real_config!r} \"$@\"\n"
            )
            config.chmod(0o755)
            for shell in ("bash", "sh"):
                for extra, expected in cases:
                    with self.subTest(shell=shell, extra=extra):
                        result = subprocess.run(
                            [shell, "-c", validity],
                            env={**os.environ, "PATH": f"{td}:{os.environ['PATH']}", **extra},
                            text=True, capture_output=True, check=False,
                        )
                        self.assertEqual(result.returncode, expected, result.stderr)

    def test_acceptance_checks_installed_ollama_guest_contract(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        names = (
            "Ollama runtime installer dry-run",
            "Ollama runtime service",
            "Ollama system service",
            "Ollama loopback listener",
            "Ollama API version",
            "Ollama PATH client",
            "Ollama Vulkan packages",
            "Ollama model weights",
            "Ollama notices",
            "wizard CLI inventory",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIn(f'"{name}",', verify)

        # Pin the guest commands behind those report names: no sudo, a strict
        # loopback-only listener, the pinned API version, and the installed
        # command line client used by both the desktop and the wizard.
        for command in (
            "--dry-run",
            "Plebian OS Ollama CPU + Vulkan runtime (offline carrier; no model weights)",
            "--verify",
            "systemctl is-enabled plebian-os-ollama.service",
            "systemctl is-active --quiet plebian-os-ollama.service",
            "ss -Htln",
            "127.0.0.1:11434",
            'command -v ollama',
            "/usr/local/bin/ollama",
            "ollama-0.32.14-kilix-unix-vulkan-r1/usr/bin/ollama",
            "OLLAMA_HOST=http://127.0.0.1:11434 timeout 15 ollama list",
            "libvulkan1",
            "mesa-vulkan-drivers",
            "firmware-nvidia-graphics",
            "! test -r /var/lib/ollama/models",
            "awk 'NR == 1",
            "/usr/share/doc/ollama-runtime/BUILD-CLOSURE",
            "find . -type f -print0 | xargs -0 -r -n1 test -r",
            "sha256sum --check --status SHA256SUMS",
            'wizard --all --json',
            "runtime_ready",
            "Uses the running local Ollama backend.",
        ):
            with self.subTest(command=command):
                self.assertIn(command, verify)
        api_predicate = vm.ollama_api_version_predicate()
        for fragment in (
            "http://127.0.0.1:11434/api/version",
            "urllib.request.ProxyHandler({})",
            "assert version == expected, (version, expected)",
            json.dumps(vm.pinned_ollama_version()),
        ):
            self.assertIn(fragment, api_predicate)

        for name, seconds in (
            ("Ollama runtime installer dry-run", 30),
            ("Ollama runtime service", 45),
            ("Ollama PATH client", 30),
            ("Ollama model weights", 30),
            ("Ollama notices", 30),
            ("wizard CLI inventory", 90),
        ):
            self.assertIn(f'"{name}": {seconds}', verify)

        # Capture, but never execute, the guest commands generated by the
        # acceptance flow and ask Bash to parse each changed command.
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_provisioning(cfg(), "askpass")
            commands = [call.args[1] for call in remote.call_args_list]
            for needle in (
                "Plebian OS Ollama CPU + Vulkan runtime (offline carrier; no model weights)",
                "systemctl is-enabled plebian-os-ollama.service",
                "ss -Htln",
                "http://127.0.0.1:11434/api/version",
                "command -v ollama",
                "dpkg-query -W",
                "! test -r /var/lib/ollama/models",
                "sha256sum --check --status SHA256SUMS",
                'wizard --all --json',
            ):
                command = next(cmd for cmd in commands if needle in cmd)
                self.assertNotIn("sudo ", command)
                parsed = subprocess.run(
                    ["/bin/bash", "-n", "-c", command],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(parsed.returncode, 0, (needle, parsed.stderr))

    def test_acceptance_checks_coherent_canonical_kilix_generation(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        self.assertIn('"kilix fork generation"', verify)
        self.assertIn("KILIX_STATE_DIRECTORY", verify)
        self.assertIn("KILIX_BUILD_DIRECTORY", verify)
        self.assertIn("current/source-id", verify)
        self.assertIn("generations/build", verify)
        self.assertIn("readlink --", verify)
        self.assertIn("fork-built-ref", verify)
        self.assertIn("launcher/kitty", verify)
        self.assertIn("launcher/kitten", verify)
        self.assertIn("rev-parse --verify HEAD", verify)
        self.assertIn("pwd -P", verify)
        self.assertIn("--which", verify)
        self.assertIn('timeout 15 "$t" --version', verify)
        self.assertIn("cmp -s", verify)
        self.assertIn("stat -c \\'%a\\'", verify)
        self.assertIn("stat -c \\'%h\\'", verify)
        self.assertIn('test ! -e "$ps/kilix-fork-built-ref"', verify)
        self.assertIn('test ! -L "$ps/kilix-fork-built-ref"', verify)

    def test_acceptance_checks_private_storage_roots(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        self.assertIn('"private storage roots"', verify)
        for root in (
            "GPU_TERMINAL_HOME",
            "PLEB_STORAGE_HOME",
            "KILIX_STORAGE_HOME",
            "KILIX95_STORAGE_HOME",
            "PLEBIAN_OS_STORAGE_HOME",
            "PLEB_CONFIG_HOME",
            "PLEB_STATE_HOME",
            "PLEB_CACHE_HOME",
            "PLEB_SESSION_HOME",
            "PLEB_DATA_HOME",
            "KILIX_CONFIG_HOME",
            "KILIX_STATE_DIRECTORY",
            "KILIX_CACHE_HOME",
            "KILIX_SESSION_HOME",
            "KILIX_BUILD_DIRECTORY",
            "KILIX_DATA_HOME",
            "KILIX_PREBUILT_HOME",
            "KILIX95_CONFIG_HOME",
            "KILIX95_STATE_HOME",
            "KILIX95_CACHE_HOME",
            "KILIX95_SESSION_HOME",
            "KILIX95_DATA_HOME",
            "PLEBIAN_OS_SESSION_HOME",
            "KILIX_DESKTOP_DIR",
        ):
            self.assertIn(root, verify)
        self.assertIn("stat -c \\'%u\\'", verify)
        self.assertIn("stat -c \\'%a\\'", verify)
        self.assertIn("readlink -m", verify)
        self.assertIn('case "$d" in "$anchor"/*)', verify)
        self.assertIn('private_dir "$HOME" "$g"', verify)
        self.assertIn('private_dir "$p" "$pc"', verify)
        self.assertIn('private_dir "$k" "$kc"', verify)
        self.assertIn('private_tree "$k" "$kp"', verify)
        self.assertIn('private_dir "$tree_root" "$tree_current"', verify)
        self.assertIn('private_dir "$n" "$nc"', verify)
        self.assertIn('private_dir "$o" "$or"', verify)
        self.assertIn('"$pd"/*) private_dir "$pd" "$w"', verify)
        self.assertIn('= 700 ];', verify)

    def test_acceptance_checks_exact_session_selection(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        self.assertIn('"session selection"', verify)
        self.assertIn('"session provenance"', verify)
        self.assertIn('"visible kilix chrome"', verify)
        self.assertIn('"first-page Kilix desktop"', verify)
        self.assertIn(
            "KILIX_ARGV=(--start-as=maximized -o "
            "hide_window_decorations=yes)",
            verify,
        )
        self.assertIn("KILIX_ARGV=(--start-as=fullscreen)", verify)
        self.assertIn("DESKTOP_ARGS=(env KILIX_IN_OVERLAY=1", verify)
        self.assertIn('\\"$KILIX\\" desktop)', verify)
        for key in (
            "PLEB_DESKTOP", "PLEB_RESPAWN", "PLEBIAN_OS_DESKTOP",
            "PLEBIAN_OS_KIOSK", "KILIX_DESKTOP_PROVIDER",
            "KILIX_DESKTOP_FLAVOR",
        ):
            self.assertIn(key, verify)

    def test_catalog_acceptance_builds_in_temporary_guest_roots(self):
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_catalog_builds(cfg(), "askpass")
        command = remote.call_args.args[1]
        self.assertIn("TemporaryDirectory", command)
        self.assertIn("default_catalog", command)
        self.assertIn("Installer", command)
        self.assertIn("spec.source_type", command)
        self.assertIn("timeout 1750 python3", command)
        self.assertEqual(remote.call_args.kwargs["timeout"], 1800)

    def test_acceptance_treats_exit_status_as_authoritative(self):
        # A failed guest command that happens to print "OK" must never pass.
        result = SimpleNamespace(returncode=1, stdout="OK\n", stderr="")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"), self.assertRaises(SystemExit):
            vm.verify_provisioning(cfg(), "askpass")
        self.assertGreater(remote.call_count, 1)

    def test_firstboot_failure_reads_system_journal_with_existing_sudo_grant(self):
        failed = SimpleNamespace(returncode=0, stdout="FAILED\n", stderr="")
        journal = SimpleNamespace(returncode=0, stdout="transaction refused\n", stderr="")
        with mock.patch.object(vm, "ssh", side_effect=(failed, journal)) as remote, \
                mock.patch.object(vm, "info"), \
                mock.patch.object(vm, "die", side_effect=SystemExit(1)) as fatal, \
                self.assertRaises(SystemExit):
            vm.wait_for_provisioning(cfg(nopasswd_sudo=True), 30, ("askpass", "credential"))
        self.assertEqual(remote.call_count, 2)
        command = remote.call_args_list[1].args[1]
        self.assertEqual(command, "sudo -n /usr/bin/journalctl -u "
                         "plebian-os-firstboot.service --no-pager -n 30")
        self.assertNotIn("strong-secret", command)
        self.assertIn("transaction refused", fatal.call_args.args[0])

    def test_firstboot_failure_falls_back_when_sudo_diagnostics_unavailable(self):
        failed = SimpleNamespace(returncode=0, stdout="FAILED\n", stderr="")
        denied = SimpleNamespace(returncode=1, stdout="", stderr="sudo unavailable\n")
        journal = SimpleNamespace(returncode=0, stdout="-- No entries --\n",
                                  stderr="system journal permission denied\n")
        for privileged_result in (denied, None):
            with self.subTest(privileged_result=privileged_result), \
                    mock.patch.object(vm, "ssh", side_effect=(failed, privileged_result, privileged_result, journal)) as remote, \
                    mock.patch.object(vm, "info"), \
                    mock.patch.object(vm, "die", side_effect=SystemExit(1)) as fatal, \
                    self.assertRaises(SystemExit):
                vm.wait_for_provisioning(cfg(nopasswd_sudo=True), 30, ("askpass", "credential"))
            self.assertEqual(remote.call_count, 4)
            self.assertTrue(remote.call_args_list[-1].args[1].startswith("/usr/bin/journalctl "))
            self.assertIn("system journal permission denied", fatal.call_args.args[0])

    def test_firstboot_failure_reads_journal_before_nopasswd_is_installed(self):
        failed = SimpleNamespace(returncode=0, stdout="FAILED\n", stderr="")
        denied = SimpleNamespace(returncode=1, stdout="", stderr="a password is required\n")
        journal = SimpleNamespace(returncode=0, stdout="Qt bundle refused\n", stderr="")
        with mock.patch.object(vm, "ssh", side_effect=(failed, denied, journal)) as remote, \
                mock.patch.object(vm, "info"), \
                mock.patch.object(vm, "die", side_effect=SystemExit(1)) as fatal, \
                self.assertRaises(SystemExit):
            vm.wait_for_provisioning(cfg(nopasswd_sudo=True), 30, ("askpass", "credential"))
        call = remote.call_args_list[-1]
        self.assertEqual(call.args[1], "sudo -S -p '' -- /usr/bin/journalctl -u "
                         "plebian-os-firstboot.service --no-pager -n 30")
        self.assertEqual(call.kwargs["stdin"], "strong-secret\n")
        self.assertNotIn("strong-secret", call.args[1])
        self.assertIn("Qt bundle refused", fatal.call_args.args[0])
        self.assertNotIn("strong-secret", fatal.call_args.args[0])

    def test_ssh_sends_diagnostic_credential_only_on_standard_input(self):
        result = SimpleNamespace(returncode=0, stdout="journal\n", stderr="")
        with mock.patch.object(vm.subprocess, "run", return_value=result) as run:
            vm.ssh(cfg(), "sudo -S -p '' -- /usr/bin/journalctl -n 30",
                   ("askpass", "credential"), stdin="strong-secret\n")
        self.assertEqual(run.call_args.kwargs["input"], "strong-secret\n")
        self.assertNotIn("strong-secret", " ".join(run.call_args.args[0]))
        self.assertNotIn("strong-secret", run.call_args.kwargs["env"].values())

    def test_firstboot_failure_uses_unprivileged_journal_without_sudo_grant(self):
        failed = SimpleNamespace(returncode=0, stdout="FAILED\n", stderr="")
        journal = SimpleNamespace(returncode=0, stdout="visible journal\n", stderr="")
        with mock.patch.object(vm, "ssh", side_effect=(failed, journal)) as remote, \
                mock.patch.object(vm, "info"), \
                mock.patch.object(vm, "die", side_effect=SystemExit(1)), \
                self.assertRaises(SystemExit):
            vm.wait_for_provisioning(cfg(nopasswd_sudo=False), 30, ("askpass", "credential"))
        self.assertEqual(remote.call_count, 2)
        self.assertTrue(remote.call_args_list[-1].args[1].startswith("/usr/bin/journalctl "))

    def test_guest_timeout_budget_counts_each_loop_iteration(self):
        command = ("timeout 5 a && for t in x y z; do timeout 10 \"$t\" || exit 1; "
                   "done && timeout 7 b")
        self.assertEqual(vm._guest_timeout_budget(command), 5 + 3 * 10 + 7 + 15)
        self.assertEqual(vm._guest_timeout_budget("true"), 15)
        self.assertEqual(vm._guest_timeout_budget(
            'while [ -n "$x" ]; do x="${x#*/}"; done; timeout 9 a'), 9 + 15)
        self.assertEqual(vm._guest_timeout_budget(
            "for t in a b c\ndo\n timeout 10 x\ndone"), 3 * 10 + 15)
        for unsupported in (
                "for x in a b; do for y in c d e; do timeout 10 n; done; done",
                'for x in a b c; do printf "%s" "done"; timeout 10 one; done',
                'while true; do timeout 10 poll; done',
                'while timeout 10 check; do printf x; done',
                'until timeout 11 check; do printf x; done',
                'while true\ndo\n timeout 10 poll\ndone',
                'for t in a b\ndo\n timeout 10 x\ndone\nfor u in c\ndo\n for v in d e\n do timeout 1 y; done\ndone'):
            with self.subTest(command=unsupported):
                with self.assertRaises(ValueError):
                    vm._guest_timeout_budget(unsupported)

    def test_voice_acceptance_host_timeout_outlives_guest_steps(self):
        # 0.1.9 fixed this with a flat 195 s; the check has since grown
        # further sequential guest steps, so the bound is derived from them.
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        for policy in ("0", "1"):
            with self.subTest(policy=policy), mock.patch.dict(
                    os.environ, {"PLEBIAN_OS_INSTALL_VOICE_MODEL": policy},
                    clear=True), \
                    mock.patch.object(vm, "ssh", return_value=result) as remote, \
                    mock.patch.object(vm, "info"):
                vm.verify_provisioning(cfg(), "askpass")
            voice_calls = [
                call for call in remote.call_args_list
                if "kilix.speech.models/v1" in call.args[1]
            ]
            self.assertEqual(len(voice_calls), 1)
            command = voice_calls[0].args[1]
            self.assertIn("timeout 180 python3", command)
            # Counted by hand: the 180 s smoke; 3 tools x 15 s --version;
            # tts --print, stt --print, stt --models and the catalog check at
            # 15 s each; policy 1 adds a second 3-tool --version loop.
            guest = {"0": 180 + 3 * 15 + 4 * 15,
                     "1": 180 + 3 * 15 + 4 * 15 + 3 * 15}[policy]
            self.assertGreater(voice_calls[0].kwargs["timeout"], guest)

    def test_update_rollback_gate_uses_real_installed_updater(self):
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_update_rollback(cfg(), "askpass")
        command = remote.call_args.args[1]
        self.assertIn("PLEBIAN_OS_UPDATE_TEST_FAIL_AFTER=os-layer", command)
        self.assertIn("/usr/local/bin/plebian-os-update", command)
        self.assertIn("snapshot_acceptance_update", command)
        self.assertIn('cmp -s "$before" "$after"', command)
        self.assertIn("/usr/local/bin/plebian-os-select-closure", command)
        for path in (
            "/usr/local/bin/uv",
            "/usr/local/bin/uvx",
            "/var/lib/plebian-os/packages.list",
            "/var/lib/plebian-os/versions.env",
            "/var/lib/plebian-os/apt-sources.list",
        ):
            self.assertIn(path, command)

    def test_successful_update_waits_for_a_new_lightdm_invocation(self):
        before = SimpleNamespace(
            returncode=0,
            stdout="0123456789abcdef0123456789abcdef\n",
            stderr="",
        )
        success = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(
                vm, "ssh", side_effect=(before, success, success)) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_successful_update(cfg(), "askpass")

        self.assertEqual(remote.call_count, 3)
        self.assertIn("InvocationID", remote.call_args_list[0].args[1])
        self.assertIn("plebian-os-update --restart", remote.call_args_list[1].args[1])
        health = remote.call_args_list[2].args[1]
        self.assertIn("timeout 45", health)
        self.assertIn("0123456789abcdef0123456789abcdef", health)
        self.assertIn('"$current" != "$1"', health)
        self.assertIn("systemctl is-active --quiet lightdm.service", health)
        self.assertIn("systemctl is-failed --quiet lightdm.service", health)
        self.assertIn("/var/lib/plebian-os/versions.env", health)
        self.assertIn('test "$PLEBIAN_OS_COMMIT" = "$selected_os"', health)
        self.assertIn("/usr/local/bin/uv --version", health)
        self.assertEqual(remote.call_args_list[2].kwargs["timeout"], 60)

    def test_successful_update_refuses_missing_lightdm_identity(self):
        missing = SimpleNamespace(returncode=0, stdout="\n", stderr="")
        with mock.patch.object(vm, "ssh", return_value=missing) as remote, \
                mock.patch.object(vm, "info"), self.assertRaises(SystemExit):
            vm.verify_successful_update(cfg(), "askpass")
        self.assertEqual(remote.call_count, 1)

    def test_catalog_acceptance_program_clean_builds_and_selects_every_pin(self):
        installed = []
        roots = []

        class Installer:
            def __init__(self, root):
                self.root = Path(root)
                roots.append(self.root)

            def executable(self, spec):
                return str(self.root / spec.content_id / spec.binary)

            def ensure(self, spec, report):
                installed.append(spec.content_id)
                report(f"building {spec.content_id}")
                executable = Path(self.executable(spec))
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.write_text("#!/bin/sh\n")
                executable.chmod(0o755)
                return str(executable)

            def ready(self, spec):
                executable = Path(self.executable(spec))
                return str(executable) if executable.is_file() else None

        specs = (
            SimpleNamespace(
                content_id="game", source_type="git", kind="game",
                binary="game",
            ),
            SimpleNamespace(
                content_id="app", source_type="archive", kind="app",
                binary="bin/app",
            ),
            SimpleNamespace(
                content_id="builtin", source_type="custom", kind="app",
                binary="",
            ),
        )
        module = ModuleType("kilix_content")
        module.Installer = Installer
        module.default_catalog = lambda: specs
        with mock.patch.dict(sys.modules, {"kilix_content": module}), \
                mock.patch("builtins.print"):
            exec(vm._catalog_build_script(), {})

        self.assertEqual(installed, ["game", "app"])
        self.assertTrue(roots)
        self.assertTrue(all(root.parent.parent == Path.home() for root in roots))
        self.assertTrue(all(not root.exists() for root in roots))

    def test_yes_mode_generates_harness_only_password(self):
        with mock.patch.object(vm, "generated_password", return_value="random-pass"):
            built = vm.gather_config(args())
        self.assertEqual(built.password, "random-pass")
        self.assertTrue(built.credential_generated)

    def test_plaintext_password_argument_is_retired(self):
        with self.assertRaises(SystemExit):
            vm.gather_config(args(password="process-visible"))

    def test_ambient_image_password_is_retired(self):
        with mock.patch.dict(os.environ, {
            "IMAGE_PASSWORD": "known-secret",
        }, clear=True), self.assertRaises(SystemExit):
            vm.gather_config(args())

    def test_ambient_random_password_switch_is_retired(self):
        with mock.patch.dict(os.environ, {
            "RANDOM_PASSWORD": "1",
        }, clear=True), self.assertRaises(SystemExit):
            vm.gather_config(args())

    def test_password_file_requires_owner_mode_0600(self):
        with tempfile.TemporaryDirectory() as td:
            credential = Path(td) / "credential"
            credential.write_text("private-secret\n")
            credential.chmod(0o644)
            with self.assertRaises(SystemExit):
                vm.gather_config(args(
                    password_file=credential,
                    generate_one_time_password=False,
                ))
            credential.chmod(0o600)
            built = vm.gather_config(args(
                password_file=credential,
                generate_one_time_password=False,
                nopasswd_sudo=False,
            ))
        self.assertEqual(built.password, "private-secret")
        self.assertFalse(built.credential_generated)

    def test_password_hash_file_avoids_plaintext_and_requires_no_wait(self):
        with tempfile.TemporaryDirectory() as td:
            credential = Path(td) / "credential.hash"
            credential.write_text("$6$abcdefghijklmnop$hashvalue0123456789\n")
            credential.chmod(0o600)
            built = vm.gather_config(args(
                password_hash_file=credential,
                generate_one_time_password=False,
                nopasswd_sudo=False,
                no_wait=True,
            ))
        self.assertEqual(built.password, "")
        self.assertTrue(built.password_hash.startswith("$6$"))

    def test_noninteractive_identity_must_be_explicit(self):
        with self.assertRaises(SystemExit):
            vm.gather_config(args(username=None))
        with self.assertRaises(SystemExit):
            vm.gather_config(args(hostname=None))

    def test_prebuilt_interactive_installer_uses_no_guest_identity_or_secret(self):
        built = vm.gather_config(args(
            interactive_installer=True,
            username=None,
            fullname=None,
            hostname=None,
            generate_one_time_password=False,
            nopasswd_sudo=None,
            no_wait=True,
            no_verify=True,
            iso=Path("strict-release.iso"),
        ))
        self.assertTrue(built.interactive_installer)
        self.assertEqual(built.username, "")
        self.assertEqual(built.hostname, "")
        self.assertEqual(built.password, "")
        self.assertEqual(built.password_hash, "")

    def test_askpass_uses_private_file_not_secret_environment(self):
        secret_value = "not-in-child-environment"
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
                vm, "storage_dir", return_value=Path(td)):
            with vm._askpass_for(secret_value) as askpass:
                secret_path = Path(askpass[1])
                self.assertEqual(secret_path.read_text().strip(), secret_value)
                self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)
                with mock.patch.object(
                        vm.subprocess, "run", return_value=result) as run:
                    vm.ssh(cfg(password=secret_value), "true", askpass)
                child_env = run.call_args.kwargs["env"]
                self.assertNotIn(secret_value, child_env.values())
                self.assertNotIn("PLEBIAN_ASKPASS_PW", child_env)
                self.assertEqual(child_env["PLEBIAN_ASKPASS_FILE"], askpass[1])
            self.assertFalse(secret_path.exists())

    def test_generated_credential_expiration_is_fail_closed(self):
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"):
            vm.expire_generated_credential(cfg(username="boundary-user"), ("a", "b"))
        command = remote.call_args.args[1]
        self.assertIn("sudo -n /usr/bin/chage -d 0", command)
        self.assertIn("boundary-user", command)

    def test_ready_generated_credential_expires_even_if_verification_fails(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        main = source[source.index("def main() -> None:"):]
        self.assertIn("finally:\n", main)
        self.assertIn("if cfg.credential_generated and provisioning_ready:", main)
        self.assertLess(
            main.index("verify_provisioning(cfg, askpass)"),
            main.index("finally:\n"),
        )
        self.assertGreater(
            main.index("expire_generated_credential(cfg, askpass)"),
            main.index("finally:\n"),
        )

    def test_defaults_to_desktop_in_first_kilix_page_and_non_kiosk(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            built = vm.gather_config(args())
        self.assertTrue(built.desktop)
        self.assertFalse(built.kiosk)

    def test_environment_session_defaults_are_honored(self):
        with mock.patch.dict(os.environ, {
            "PLEBIAN_OS_DESKTOP": "yes",
            "PLEBIAN_OS_KIOSK": "on",
            "PLEBIAN_OS_NOPASSWD_SUDO": "no",
        }, clear=True), mock.patch.object(
                vm, "resolve_automated_credential",
                return_value=("private-secret", "", False)):
            built = vm.gather_config(args(
                generate_one_time_password=False,
                nopasswd_sudo=None,
            ))
        self.assertTrue(built.desktop)
        self.assertTrue(built.kiosk)
        self.assertFalse(built.nopasswd_sudo)

    def test_explicit_session_flags_override_environment_defaults(self):
        with mock.patch.dict(os.environ, {
            "PLEBIAN_OS_DESKTOP": "1",
            "PLEBIAN_OS_KIOSK": "1",
        }, clear=True):
            built = vm.gather_config(args(session="shell", kiosk=False))
        self.assertFalse(built.desktop)
        self.assertFalse(built.kiosk)

    def test_invalid_environment_boolean_fails_closed(self):
        with mock.patch.dict(os.environ, {"PLEBIAN_OS_DESKTOP": "sometimes"},
                             clear=True), self.assertRaises(SystemExit):
            vm.gather_config(args())

    def test_vram_is_capped_to_virtualbox_limit(self):
        built = vm.gather_config(args(vram=512, accelerate_3d=True))
        self.assertEqual(built.vram_mb, 256)
        self.assertTrue(built.accelerate_3d)

    def test_firmware_defaults_to_bios_and_accepts_efi(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(vm.gather_config(args()).firmware, "bios")
            self.assertEqual(
                vm.gather_config(args(firmware="efi")).firmware,
                "efi",
            )

    def test_default_hostname_sanitizes_versioned_vm_name(self):
        self.assertEqual(
            vm.default_hostname("plebian-acceptance-0.1.9-deadbeef"),
            "plebian-acceptance-0-1-9-deadbeef",
        )

    def test_default_ram_uses_release_tested_floor(self):
        with mock.patch.object(vm, "host_ram_mb", return_value=8192):
            self.assertEqual(vm.default_ram_mb(), 4096)
        with mock.patch.object(vm, "host_ram_mb", return_value=32768):
            self.assertEqual(vm.default_ram_mb(), 8192)

    def test_explicit_low_ram_is_honored_with_warning(self):
        with mock.patch.object(vm, "warn") as warn:
            built = vm.gather_config(args(ram=2048))
        self.assertEqual(built.ram_mb, 2048)
        self.assertIn("below the 4096 MB release-tested", warn.call_args.args[0])

    def test_identity_values_are_rejected_before_preseed_or_vbox(self):
        bad = (
            dict(name="../escape"),
            dict(username="root;touch-x"),
            dict(username="root"),
            dict(username="_service"),
            dict(fullname="Name:newline"),
            dict(hostname="bad host"),
            dict(password="bad\nsecret"),
        )
        for values in bad:
            with self.subTest(values=values), self.assertRaises(SystemExit):
                vm.validate_identity(**{
                    "name": "test", "username": "pleb", "fullname": "Plebian User",
                    "password": "secret", "hostname": "test", **values,
                })

    def test_existing_vm_needs_explicit_replace(self):
        with mock.patch.object(vm, "vbox_exists", return_value=True), \
                mock.patch.object(vm, "run") as run:
            with self.assertRaises(SystemExit):
                vm.vbox_create(cfg(), Path("image.iso"), assume_yes=True)
        run.assert_not_called()

    def test_replace_and_yes_is_the_explicit_delete_gate(self):
        calls = []
        with mock.patch.object(vm, "vbox_exists", return_value=True), \
                mock.patch.object(vm, "run", side_effect=lambda argv, **_kw: calls.append(argv)), \
                mock.patch.object(vm, "vbox_info", return_value={"CfgFile": "/tmp/test/test.vbox"}), \
                mock.patch.object(vm.subprocess, "run"), \
                mock.patch.object(vm.time, "sleep"):
            vm.vbox_create(cfg(), Path("image.iso"), replace=True, assume_yes=True)
        self.assertIn(["VBoxManage", "unregistervm", "test", "--delete"], calls)

    def test_virtualbox_exposes_audio_and_hotpluggable_install_media(self):
        calls = []
        with mock.patch.object(vm, "vbox_exists", return_value=False), \
                mock.patch.object(
                    vm, "run", side_effect=lambda argv, **_kw: calls.append(argv)
                ), \
                mock.patch.object(
                    vm, "vbox_info",
                    return_value={"CfgFile": "/tmp/test/test.vbox"},
                ):
            vm.vbox_create(cfg(), Path("image.iso"))

        modify = next(call for call in calls if call[:2] == ["VBoxManage", "modifyvm"])
        self.assertEqual(modify[modify.index("--audio-enabled") + 1], "on")
        self.assertEqual(modify[modify.index("--audio-in") + 1], "on")
        self.assertEqual(modify[modify.index("--audio-out") + 1], "on")
        self.assertEqual(modify[modify.index("--firmware") + 1], "bios")
        dvd = next(call for call in calls if
                   call[:2] == ["VBoxManage", "storageattach"] and
                   "dvddrive" in call)
        self.assertEqual(dvd[dvd.index("--hotpluggable") + 1], "on")

    def test_iso_detach_failure_is_fatal(self):
        failed = SimpleNamespace(returncode=1, stdout="", stderr="busy")
        with mock.patch.object(vm, "vbox_info", return_value={
                "SATA-1-0": "/tmp/installer.iso",
        }), mock.patch.object(vm.subprocess, "run", return_value=failed), \
                self.assertRaises(SystemExit):
            vm.vbox_detach_iso(cfg())

    def test_iso_detach_is_idempotent_after_guest_eject(self):
        with mock.patch.object(vm, "vbox_info", return_value={
                "SATA-1-0": "emptydrive",
                "SATA-IsEjected-1-0": "on",
        }), mock.patch.object(vm.subprocess, "run") as detach:
            vm.vbox_detach_iso(cfg())
        detach.assert_not_called()

    def test_acceptance_report_is_nonsecret_and_checksummed(self):
        git_results = [
            SimpleNamespace(stdout="a" * 40 + "\n"),
            SimpleNamespace(stdout=""),
        ]
        with mock.patch.object(
                vm, "run", return_value=SimpleNamespace(stdout="7.1.0\n")), \
                mock.patch.object(
                    vm.subprocess, "run", side_effect=git_results):
            initial = vm.acceptance_report_initial(cfg(), args())
        serialized = json.dumps(initial)
        self.assertNotIn("strong-secret", serialized)
        self.assertNotIn(str(vm.REPO), serialized)

        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "acceptance.json"
            iso = Path(td) / "candidate.iso"
            iso.write_bytes(b"candidate bytes")
            recorder = vm.AcceptanceRecorder(report, initial)
            recorder.stage("preflight")
            recorder.set_iso(iso)
            recorder.check("guest check", True)
            recorder.complete()
            parsed = json.loads(report.read_text())
            self.assertEqual(parsed["status"], "passed")
            self.assertEqual(parsed["stages"][0]["name"], "preflight")
            self.assertEqual(parsed["iso"]["filename"], "candidate.iso")
            self.assertNotIn(td, json.dumps(parsed))
            checksum = hashlib.sha256(report.read_bytes()).hexdigest()
            self.assertEqual(
                (Path(str(report) + ".sha256")).read_text(),
                f"{checksum}  {report.name}\n",
            )

    def test_openssl_failure_never_falls_back_to_plaintext(self):
        result = SimpleNamespace(returncode=1, stdout="", stderr="failed")
        with mock.patch.object(vm, "have", return_value=True), \
                mock.patch.object(vm.subprocess, "run", return_value=result), \
                self.assertRaises(SystemExit):
            vm.crypt_password("secret")


if __name__ == "__main__":
    unittest.main()
