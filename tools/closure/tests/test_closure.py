from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kilix_f120.canonical import atomic_write_json, file_sha256
from kilix_f120.cache import evict_entry
from kilix_f120.contracts import validate_path, verify_contract_package
from kilix_f120.errors import BuildError, ContractError, RegistrationError
from kilix_f120.graph import reverse_dependencies
from kilix_f120.keys import build_key_sha256
from kilix_f120.manifest import emit_workspace_manifest
from kilix_f120.registration import load_registration
from kilix_f120.stage import retire_stage, stage_workspace


def concurrent_stage_worker(
    registration_path: str,
    manifest_path: str,
    cache: str,
    prefix: str,
    lock: str,
    repository: str,
    queue,
) -> None:
    try:
        registration = load_registration(Path(registration_path))
        manifest = validate_path(Path(manifest_path))
        report = stage_workspace(
            registration,
            manifest,
            cache=Path(cache),
            destination=Path(prefix),
            release="0.2.1",
            release_lock=Path(lock),
            local_sources={"provider": Path(repository)},
        )
        queue.put((report.fetches, report.builds, ""))
    except BaseException as exc:
        queue.put((-1, -1, f"{type(exc).__name__}: {exc}"))


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "user.name=F120 Test",
            "-c",
            "user.email=f120-test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repository),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_ASKPASS": "/bin/false",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
        },
    )
    return result.stdout.strip()


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def independent_source_sha256(repository: Path, commit: str) -> str:
    environment = {
        "GIT_ASKPASS": "/bin/false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }

    def output(*arguments: str) -> bytes:
        return subprocess.run(
            ["git", "-c", "credential.helper=", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            env=environment,
        ).stdout

    def field(digest, value: bytes) -> None:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    digest = hashlib.sha256(b"kilix.f120.source-tree/v1\0")
    count = 0
    for record in output("ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not record:
            continue
        header, path = record.split(b"\t", 1)
        mode, kind, object_id = header.split(b" ", 2)
        for value in (mode, kind, object_id, path):
            field(digest, value)
        field(
            digest,
            output("cat-file", "blob", object_id.decode()) if kind == b"blob" else b"",
        )
        count += 1
    digest.update(count.to_bytes(8, "big"))
    return digest.hexdigest()


class ClosureIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.repository = self.workspace / "provider"
        self.repository.mkdir(parents=True)
        git(self.repository, "init", "--initial-branch=main")
        license_bytes = b"test license\n"
        (self.repository / "LICENSE").write_bytes(license_bytes)
        (self.repository / "payload.txt").write_bytes(b"stable provider artifact\n")
        git(self.repository, "add", "LICENSE", "payload.txt")
        git(self.repository, "commit", "-m", "provider fixture")
        self.commit = git(self.repository, "rev-parse", "HEAD")
        copy_tool = Path(shutil.which("cp") or "/usr/bin/cp").resolve()
        self.registration_path = self.root / "registration.json"
        self.registration_document = {
            "components": [
                {
                    "abi_version": "1",
                    "api_version": "1",
                    "architecture": "x86_64-linux-gnu",
                    "build": {
                        "artifacts": [
                            {
                                "artifact_id": "provider-data",
                                "artifact_kind": "data",
                                "path": "share/provider/payload.txt",
                            }
                        ],
                        "commands": [
                            [
                                "{tool:cp}",
                                "{source}/payload.txt",
                                "{source}/built.txt",
                            ]
                        ],
                        "copies": [
                            {
                                "destination": "share/provider/payload.txt",
                                "mode": 420,
                                "source": "built.txt",
                            }
                        ],
                        "environment": {},
                    },
                    "build_options": {},
                    "canonical_url": "https://github.com/example/provider.git",
                    "component_id": "example-provider",
                    "component_version": "1.0.0",
                    "expected_commit": self.commit,
                    "features": ["fixture"],
                    "instance_id": "provider",
                    "licenses": [
                        {
                            "spdx": "MIT",
                            "text_sha256": hashlib.sha256(license_bytes).hexdigest(),
                        }
                    ],
                    "notices": [
                        {
                            "path": "LICENSE",
                            "sha256": hashlib.sha256(license_bytes).hexdigest(),
                        }
                    ],
                    "path": "provider",
                    "publication_disposition": "publish",
                    "ref_kind": "exact-commit",
                    "requested_ref": self.commit,
                    "required_tests": ["unit"],
                    "runtime_kind": "native-provider",
                    "toolchain": {
                        "executables": [
                            {
                                "name": "cp",
                                "path": str(copy_tool),
                                "sha256": file_sha256(copy_tool),
                            }
                        ],
                        "name": "coreutils",
                        "version": "fixture",
                    },
                    "visibility": "public",
                }
            ],
            "dependencies": [],
            "schema": "kilix.f120.registration/v1",
            "workspace_root": str(self.workspace),
        }
        atomic_write_json(self.registration_path, self.registration_document)
        self.registration = load_registration(self.registration_path)
        self.manifest_path = self.root / "workspace.json"
        self.manifest = emit_workspace_manifest(
            self.registration,
            self.manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def stage(self, cache: Path, name: str):
        return stage_workspace(
            self.registration,
            self.manifest,
            cache=cache,
            destination=self.root / name,
            release="0.2.1",
            release_lock=self.root / f"{name}.lock.json",
            local_sources={"provider": self.repository},
        )

    def test_cold_warm_and_clean_cache_are_exact(self) -> None:
        cache = self.root / "cache"
        cold = self.stage(cache, "stage-cold")
        warm = self.stage(cache, "stage-warm")
        clean = self.stage(self.root / "clean-cache", "stage-clean")

        self.assertEqual((cold.fetches, cold.builds), (1, 1))
        self.assertEqual((warm.fetches, warm.builds), (0, 0))
        self.assertEqual((warm.source_cache_hits, warm.build_cache_hits), (1, 1))
        self.assertEqual((clean.fetches, clean.builds), (1, 1))
        self.assertEqual(
            tree_bytes(self.root / "stage-cold"), tree_bytes(self.root / "stage-warm")
        )
        self.assertEqual(
            tree_bytes(self.root / "stage-cold"), tree_bytes(self.root / "stage-clean")
        )
        self.assertEqual(
            (self.root / "stage-cold.lock.json").read_bytes(),
            (self.root / "stage-clean.lock.json").read_bytes(),
        )
        validate_path(self.root / "stage-cold.lock.json")
        metadata = b"".join(path.read_bytes() for path in cache.rglob("metadata.json"))
        self.assertNotIn(str(self.root).encode(), metadata)

    def test_source_digest_matches_independent_reader(self) -> None:
        self.assertEqual(
            self.manifest["components"][0]["source_sha256"],
            independent_source_sha256(self.repository, self.commit),
        )

    def test_corrupt_source_entry_is_quarantined_and_refetched(self) -> None:
        cache = self.root / "cache"
        cold = self.stage(cache, "stage-one")
        self.assertEqual(cold.fetches, 1)
        source_metadata = next((cache / "sources" / "sha256").glob("*/metadata.json"))
        source_metadata.write_text("{}\n", encoding="utf-8")
        recovered = self.stage(cache, "stage-two")
        self.assertEqual(recovered.fetches, 1)
        self.assertEqual(recovered.builds, 0)
        self.assertTrue(any((cache / "quarantine" / "sources").iterdir()))

    def test_concurrent_writers_fetch_and_build_once(self) -> None:
        context = multiprocessing.get_context("fork")
        queue = context.Queue()
        cache = self.root / "concurrent-cache"
        processes = [
            context.Process(
                target=concurrent_stage_worker,
                args=(
                    str(self.registration_path),
                    str(self.manifest_path),
                    str(cache),
                    str(self.root / f"concurrent-stage-{index}"),
                    str(self.root / f"concurrent-{index}.lock.json"),
                    str(self.repository),
                    queue,
                ),
            )
            for index in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
        results = [queue.get(timeout=2) for _ in processes]
        self.assertEqual([item[2] for item in results], ["", ""])
        self.assertEqual(sum(item[0] for item in results), 1)
        self.assertEqual(sum(item[1] for item in results), 1)
        self.assertEqual(
            tree_bytes(self.root / "concurrent-stage-0"),
            tree_bytes(self.root / "concurrent-stage-1"),
        )

    def test_cancelled_build_publishes_nothing(self) -> None:
        document = copy.deepcopy(self.registration_document)
        sleep_tool = Path(shutil.which("sleep") or "/usr/bin/sleep").resolve()
        component = document["components"][0]
        component["toolchain"] = {
            "executables": [
                {
                    "name": "sleep",
                    "path": str(sleep_tool),
                    "sha256": file_sha256(sleep_tool),
                }
            ],
            "name": "coreutils",
            "version": "fixture",
        }
        component["build"]["commands"] = [["{tool:sleep}", "10"]]
        registration_path = self.root / "cancel-registration.json"
        atomic_write_json(registration_path, document)
        registration = load_registration(registration_path)
        manifest_path = self.root / "cancel-workspace.json"
        manifest = emit_workspace_manifest(
            registration,
            manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        cache = self.root / "cancel-cache"
        prefix = self.root / "cancel-stage"
        lock = self.root / "cancel-lock.json"
        with mock.patch("kilix_f120.build_cache.BUILD_TIMEOUT_SECONDS", 0.05):
            with self.assertRaises(BuildError):
                stage_workspace(
                    registration,
                    manifest,
                    cache=cache,
                    destination=prefix,
                    release="0.2.1",
                    release_lock=lock,
                    local_sources={"provider": self.repository},
                )
        self.assertFalse(prefix.exists())
        self.assertFalse(lock.exists())
        self.assertFalse(any((cache / "builds" / "sha256").glob("*")))

    def test_exact_eviction_and_stage_retirement_are_recoverable(self) -> None:
        cache = self.root / "cache"
        self.stage(cache, "installed")
        source_key = next((cache / "sources" / "sha256").iterdir()).name
        quarantined = evict_entry(cache, "sources", source_key)
        self.assertIsNotNone(quarantined)
        assert quarantined is not None
        self.assertTrue(quarantined.is_dir())
        self.assertFalse((cache / "sources" / "sha256" / source_key).exists())
        retirement = retire_stage(
            self.root / "installed", self.root / "installed.lock.json"
        )
        self.assertTrue((retirement / "prefix").is_dir())
        self.assertTrue((retirement / "release-lock.json").is_file())
        self.assertFalse((self.root / "installed").exists())

    def test_registration_rejects_reserved_build_environment(self) -> None:
        document = copy.deepcopy(self.registration_document)
        document["components"][0]["build"]["environment"] = {"HOME": "/tmp"}
        path = self.root / "reserved-environment.json"
        atomic_write_json(path, document)
        with self.assertRaises(RegistrationError):
            load_registration(path)

    def test_unresolved_component_is_development_only(self) -> None:
        document = copy.deepcopy(self.registration_document)
        document["components"][0]["path"] = "missing"
        path = self.root / "unresolved-registration.json"
        atomic_write_json(path, document)
        registration = load_registration(path)
        manifest_path = self.root / "unresolved.json"
        manifest = emit_workspace_manifest(registration, manifest_path)
        self.assertEqual(manifest["components"][0]["resolution_state"], "unresolved")
        with self.assertRaises(ContractError):
            validate_path(manifest_path)


class ContractPolicyTest(unittest.TestCase):
    def test_frozen_contract_package_is_intact(self) -> None:
        verify_contract_package()

    def test_named_v020_tag_exception_only(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[1]
            / "contracts"
            / "fixtures"
            / "valid"
            / "workspace-clean.json"
        )
        document = json.loads(fixture.read_text(encoding="utf-8"))
        component = document["components"][0]
        component["component_id"] = "plebian-os"
        component["ref_kind"] = "tag"
        component["requested_ref"] = "v0.2.0"
        with tempfile.TemporaryDirectory() as temporary:
            accepted = Path(temporary) / "accepted.json"
            atomic_write_json(accepted, document)
            validate_path(accepted)
            component["requested_ref"] = "v0.2.1"
            rejected = Path(temporary) / "rejected.json"
            atomic_write_json(rejected, document)
            with self.assertRaises(ContractError):
                validate_path(rejected)

    def test_build_key_changes_for_every_frozen_dimension(self) -> None:
        component = {
            "architecture": "x86_64-linux-gnu",
            "build_options": {"release": True},
            "features": ["simd"],
            "source_sha256": "1" * 64,
            "toolchain": {"digest": "2" * 64},
        }
        baseline = build_key_sha256(component)
        mutations = [
            ("architecture", "aarch64-linux-gnu"),
            ("build_options", {"release": False}),
            ("features", ["scalar"]),
            ("source_sha256", "3" * 64),
            ("toolchain", {"digest": "4" * 64}),
        ]
        for field, value in mutations:
            changed = copy.deepcopy(component)
            changed[field] = value
            self.assertNotEqual(baseline, build_key_sha256(changed), field)

    def test_reverse_dependencies_are_deterministic_and_transitive(self) -> None:
        document = {
            "components": [
                {"instance_id": "app"},
                {"instance_id": "middle"},
                {"instance_id": "provider"},
            ],
            "dependencies": [
                {"from": "app", "to": "middle"},
                {"from": "middle", "to": "provider"},
            ],
        }
        self.assertEqual(
            reverse_dependencies(document, {"provider"}), ["app", "middle"]
        )
        self.assertEqual(
            reverse_dependencies(document, {"provider"}, transitive=False), ["middle"]
        )

    def test_future_component_scaffolds_emit_development_manifests(self) -> None:
        fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "registrations"
        total = 0
        with tempfile.TemporaryDirectory() as temporary:
            for fixture in sorted(fixture_root.glob("*.json")):
                registration = load_registration(fixture)
                total += len(registration.components)
                output = Path(temporary) / fixture.name
                document = emit_workspace_manifest(registration, output)
                self.assertTrue(
                    all(
                        component["resolution_state"] == "unresolved"
                        for component in document["components"]
                    )
                )
                validate_path(output, allow_development_state=True)
                with self.assertRaises(ContractError):
                    validate_path(output)
        self.assertEqual(total, 10)


if __name__ == "__main__":
    unittest.main()
