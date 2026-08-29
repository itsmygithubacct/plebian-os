from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kilix_f120.assembly import assemble_registration
from kilix_f120.canonical import (
    atomic_write_json,
    canonical_bytes,
    file_sha256,
    load_json,
)
from kilix_f120.cache import evict_entry
from kilix_f120.cli import parser as cli_parser
from kilix_f120.contracts import validate_path, verify_contract_package
from kilix_f120.errors import (
    BuildError,
    ClosureError,
    ContractError,
    GitError,
    RegistrationError,
)
from kilix_f120.gitops import canonical_https_url
from kilix_f120.graph import reverse_dependencies
from kilix_f120.keys import build_key_sha256
from kilix_f120.manifest import emit_workspace_manifest
from kilix_f120.registration import load_registration
from kilix_f120.source_cache import ensure_source
from kilix_f120.stage import _staged_build_order, retire_stage, stage_workspace


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


def git(
    repository: Path,
    *arguments: str,
    extra_environment: dict[str, str] | None = None,
) -> str:
    environment = {
        "GIT_ASKPASS": "/bin/false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    environment.update(extra_environment or {})
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
        env=environment,
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
                                "kind": "native",
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
            "schema": "kilix.f120.registration/v2",
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

    def owner_fragment_documents(self) -> dict[str, dict[str, object]]:
        documents: dict[str, dict[str, object]] = {}
        for owner in ("f106", "f110", "f111"):
            component = copy.deepcopy(self.registration_document["components"][0])
            component.update(
                {
                    "component_id": f"example-{owner}",
                    "instance_id": owner,
                    "path": f"components/{owner}",
                }
            )
            component["build"]["artifacts"][0].update(
                {
                    "artifact_id": f"{owner}-data",
                    "path": f"share/{owner}/payload.txt",
                }
            )
            component["build"]["copies"][0]["destination"] = (
                f"share/{owner}/payload.txt"
            )
            dependencies: list[dict[str, object]] = []
            if owner == "f110":
                component["build"]["environment"] = {
                    "F120_INPUT_PROVIDER": "{dependency:f106}"
                }
                dependencies.append(
                    {
                        "consumption_mode": "staged-prefix",
                        "from": "f110",
                        "required_abi_version": "1",
                        "required_api_version": "1",
                        "required_tests": ["unit"],
                        "runtime_process": "none",
                        "to": "f106",
                    }
                )
            documents[owner] = {
                "components": [component],
                "dependencies": dependencies,
                "schema": "kilix.f120.registration/v2",
                "workspace_root": str(self.workspace),
            }
        return documents

    def write_owner_fragments(
        self, documents: dict[str, dict[str, object]], label: str
    ) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        for owner, document in documents.items():
            path = self.root / f"{label}-{owner}.json"
            atomic_write_json(path, document)
            paths[owner] = path
        return paths

    def test_cold_warm_and_clean_cache_are_exact(self) -> None:
        cache = self.root / "cache"
        cold = self.stage(cache, "stage-cold")
        warm = self.stage(cache, "stage-warm")
        clean = self.stage(self.root / "clean-cache", "stage-clean")

        self.assertEqual((cold.fetches, cold.builds), (1, 1))
        self.assertGreater(cold.fetch_bytes, 0)
        self.assertEqual((warm.fetches, warm.builds), (0, 0))
        self.assertEqual(warm.fetch_bytes, 0)
        self.assertEqual((warm.source_cache_hits, warm.build_cache_hits), (1, 1))
        self.assertEqual((clean.fetches, clean.builds), (1, 1))
        self.assertEqual(clean.fetch_bytes, cold.fetch_bytes)
        self.assertEqual(cold.document()["schema"], "kilix.f120.stage-report/v1")
        cold_report = cold.evidence_document()
        warm_report = warm.evidence_document()
        self.assertEqual(
            cold_report["schema"], "kilix.f120.stage-evidence-report/v1"
        )
        self.assertEqual(cold_report["summary"], cold.document())
        self.assertEqual(cold_report["build_order"], ["provider"])
        self.assertEqual(len(cold_report["source_receipts"]), 1)
        self.assertEqual(len(cold_report["build_receipts"]), 1)
        self.assertEqual(
            (
                cold_report["source_receipts"][0]["cache_hit"],
                cold_report["source_receipts"][0]["fetches"],
                cold_report["build_receipts"][0]["cache_hit"],
                cold_report["build_receipts"][0]["builds"],
            ),
            (False, 1, False, 1),
        )
        self.assertEqual(
            (
                warm_report["source_receipts"][0]["cache_hit"],
                warm_report["source_receipts"][0]["fetches"],
                warm_report["source_receipts"][0]["fetch_bytes"],
                warm_report["build_receipts"][0]["cache_hit"],
                warm_report["build_receipts"][0]["builds"],
            ),
            (True, 0, 0, True, 0),
        )
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

    def test_source_cache_fetches_one_committed_tree_once_across_instances(self) -> None:
        cache = self.root / "shared-source-cache"
        first_component = copy.deepcopy(self.manifest["components"][0])
        second_component = copy.deepcopy(first_component)
        second_component["component_id"] = "second-owner-component"
        second_component["instance_id"] = "second-owner"
        first = ensure_source(cache, first_component, local_source=self.repository)
        second = ensure_source(cache, second_component, local_source=self.repository)
        self.assertEqual((first.fetches, second.fetches), (1, 0))
        self.assertEqual((first.hit, second.hit), (False, True))
        self.assertEqual(first.repository, second.repository)
        self.assertEqual(
            len(list((cache / "sources" / "sha256").iterdir())), 1
        )

    def test_stage_cli_emits_opt_in_evidence_without_changing_summary(self) -> None:
        evidence = self.root / "cli-stage-evidence.json"
        arguments = cli_parser().parse_args(
            [
                "stage",
                str(self.registration_path),
                str(self.manifest_path),
                "--cache",
                str(self.root / "cli-stage-cache"),
                "--prefix",
                str(self.root / "cli-stage-prefix"),
                "--release",
                "0.2.1",
                "--release-lock",
                str(self.root / "cli-stage.lock.json"),
                "--evidence-report",
                str(evidence),
                "--local-source",
                f"provider={self.repository}",
            ]
        )
        with mock.patch("kilix_f120.cli._print_json") as print_json:
            self.assertEqual(arguments.handler(arguments), 0)
        summary = print_json.call_args.args[0]
        evidence_document = load_json(evidence)
        self.assertEqual(summary["schema"], "kilix.f120.stage-report/v1")
        self.assertEqual(
            evidence_document["schema"],
            "kilix.f120.stage-evidence-report/v1",
        )
        self.assertEqual(evidence_document["summary"], summary)

    def test_stage_cli_retires_publication_when_evidence_write_fails(self) -> None:
        prefix = self.root / "failed-evidence-prefix"
        release_lock = self.root / "failed-evidence.lock.json"
        arguments = cli_parser().parse_args(
            [
                "stage",
                str(self.registration_path),
                str(self.manifest_path),
                "--cache",
                str(self.root / "failed-evidence-cache"),
                "--prefix",
                str(prefix),
                "--release",
                "0.2.1",
                "--release-lock",
                str(release_lock),
                "--evidence-report",
                str(self.root / "failed-evidence-report.json"),
                "--local-source",
                f"provider={self.repository}",
            ]
        )
        with mock.patch(
            "kilix_f120.cli.atomic_write_json_new",
            side_effect=OSError("injected evidence publication failure"),
        ):
            with self.assertRaisesRegex(OSError, "injected evidence"):
                arguments.handler(arguments)
        self.assertFalse(prefix.exists())
        self.assertFalse(release_lock.exists())
        retired = prefix.parent / ".kilix-f120-retired"
        self.assertEqual(len(list(retired.iterdir())), 1)

    def test_stage_cli_refuses_evidence_inside_the_publication(self) -> None:
        prefix = self.root / "report-inside-prefix"
        arguments = cli_parser().parse_args(
            [
                "stage",
                str(self.registration_path),
                str(self.manifest_path),
                "--cache",
                str(self.root / "report-inside-cache"),
                "--prefix",
                str(prefix),
                "--release",
                "0.2.1",
                "--release-lock",
                str(self.root / "report-inside.lock.json"),
                "--evidence-report",
                str(prefix / "evidence.json"),
            ]
        )
        with mock.patch("kilix_f120.cli.stage_workspace") as stage:
            with self.assertRaisesRegex(ClosureError, "outside the staged prefix"):
                arguments.handler(arguments)
        stage.assert_not_called()

    def test_owner_fragment_assembly_is_order_independent(self) -> None:
        paths = self.write_owner_fragments(
            self.owner_fragment_documents(), "order-independent"
        )
        first_output = self.root / "assembled-first.json"
        first_report = self.root / "assembled-first-report.json"
        second_output = self.root / "assembled-second.json"
        second_report = self.root / "assembled-second-report.json"
        first = assemble_registration(
            [("f111", paths["f111"]), ("f106", paths["f106"]), ("f110", paths["f110"])],
            ["f110", "f111", "f106"],
            workspace_root=self.workspace,
            output=first_output,
            report=first_report,
        )
        second = assemble_registration(
            [("f110", paths["f110"]), ("f111", paths["f111"]), ("f106", paths["f106"])],
            ["f106", "f110", "f111"],
            workspace_root=self.workspace,
            output=second_output,
            report=second_report,
        )
        self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
        self.assertEqual(first_report.read_bytes(), second_report.read_bytes())
        self.assertEqual(first, second)
        self.assertEqual(
            (
                first["components"],
                first["dependencies"],
                first["staged_prefix_edges"],
                first["artifacts"],
            ),
            (3, 1, 1, 3),
        )
        self.assertEqual(first["required_owners"], ["f106", "f110", "f111"])
        self.assertEqual(first["build_order"], ["f106", "f110", "f111"])
        self.assertEqual(
            first["registration_sha256"], file_sha256(first_output)
        )
        load_registration(first_output)

    def test_owner_fragment_assembly_cli_uses_explicit_absolute_inputs(self) -> None:
        paths = self.write_owner_fragments(self.owner_fragment_documents(), "cli")
        output = self.root / "cli-assembled.json"
        report = self.root / "cli-assembled-report.json"
        arguments = cli_parser().parse_args(
            [
                "assemble",
                str(output),
                "--workspace-root",
                str(self.workspace),
                "--report",
                str(report),
                "--required-owner",
                "f106",
                "--fragment",
                f"f106={paths['f106']}",
                "--required-owner",
                "f110",
                "--fragment",
                f"f110={paths['f110']}",
                "--required-owner",
                "f111",
                "--fragment",
                f"f111={paths['f111']}",
            ]
        )
        with mock.patch("kilix_f120.cli._print_json") as print_json:
            self.assertEqual(arguments.handler(arguments), 0)
        print_json.assert_called_once()
        self.assertTrue(output.is_file())
        self.assertTrue(report.is_file())
        self.assertEqual(
            load_json(report)["registration_sha256"], file_sha256(output)
        )

    def test_owner_fragment_assembly_refuses_owner_set_drift(self) -> None:
        paths = self.write_owner_fragments(self.owner_fragment_documents(), "owner-drift")
        cases = {
            "missing": (
                [("f106", paths["f106"]), ("f110", paths["f110"])],
                ["f106", "f110", "f111"],
            ),
            "unexpected": (
                [
                    ("f106", paths["f106"]),
                    ("f110", paths["f110"]),
                    ("f111", paths["f111"]),
                    ("extra", paths["f111"]),
                ],
                ["f106", "f110", "f111"],
            ),
            "duplicate": (
                [("f106", paths["f106"]), ("f106", paths["f110"])],
                ["f106"],
            ),
        }
        for label, (fragments, required) in cases.items():
            with self.subTest(label=label):
                output = self.root / f"owner-{label}.json"
                report = self.root / f"owner-{label}-report.json"
                with self.assertRaises(RegistrationError):
                    assemble_registration(
                        fragments,
                        required,
                        workspace_root=self.workspace,
                        output=output,
                        report=report,
                    )
                self.assertFalse(output.exists())
                self.assertFalse(report.exists())

        symlink = self.root / "owner-fragment-symlink.json"
        symlink.symlink_to(paths["f106"])
        symlink_output = self.root / "owner-symlink.json"
        symlink_report = self.root / "owner-symlink-report.json"
        with self.assertRaises(RegistrationError):
            assemble_registration(
                [
                    ("f106", symlink),
                    ("f110", paths["f110"]),
                    ("f111", paths["f111"]),
                ],
                ["f106", "f110", "f111"],
                workspace_root=self.workspace,
                output=symlink_output,
                report=symlink_report,
            )
        self.assertFalse(symlink_output.exists())
        self.assertFalse(symlink_report.exists())

    def test_owner_fragment_assembly_refuses_release_preflight_mutations(self) -> None:
        def zero_commit(documents: dict[str, dict[str, object]]) -> None:
            documents["f106"]["components"][0]["expected_commit"] = "0" * 40

        def missing_build(documents: dict[str, dict[str, object]]) -> None:
            del documents["f111"]["components"][0]["build"]

        def api_mismatch(documents: dict[str, dict[str, object]]) -> None:
            documents["f110"]["dependencies"][0]["required_api_version"] = "2"

        def recipe_mismatch(documents: dict[str, dict[str, object]]) -> None:
            documents["f110"]["components"][0]["build"]["environment"] = {}

        def unknown_endpoint(documents: dict[str, dict[str, object]]) -> None:
            documents["f110"]["dependencies"][0]["to"] = "missing"

        def duplicate_component(documents: dict[str, dict[str, object]]) -> None:
            documents["f110"]["components"][0]["instance_id"] = "f106"

        def artifact_collision(documents: dict[str, dict[str, object]]) -> None:
            source = documents["f106"]["components"][0]["build"]
            target = documents["f111"]["components"][0]["build"]
            target["artifacts"][0]["artifact_id"] = source["artifacts"][0]["artifact_id"]

        def dependency_cycle(documents: dict[str, dict[str, object]]) -> None:
            documents["f106"]["components"][0]["build"]["environment"] = {
                "F120_INPUT_PROVIDER": "{dependency:f110}"
            }
            documents["f106"]["dependencies"].append(
                {
                    "consumption_mode": "staged-prefix",
                    "from": "f106",
                    "required_abi_version": "1",
                    "required_api_version": "1",
                    "required_tests": ["unit"],
                    "runtime_process": "none",
                    "to": "f110",
                }
            )

        mutations = {
            "zero-commit": zero_commit,
            "missing-build": missing_build,
            "api-mismatch": api_mismatch,
            "recipe-mismatch": recipe_mismatch,
            "unknown-endpoint": unknown_endpoint,
            "duplicate-component": duplicate_component,
            "artifact-collision": artifact_collision,
            "dependency-cycle": dependency_cycle,
        }
        for index, (label, mutate) in enumerate(mutations.items()):
            with self.subTest(label=label):
                documents = self.owner_fragment_documents()
                mutate(documents)
                paths = self.write_owner_fragments(documents, f"mutation-{index}")
                output = self.root / f"mutation-{index}.json"
                report = self.root / f"mutation-{index}-report.json"
                with self.assertRaises(RegistrationError):
                    assemble_registration(
                        [(owner, paths[owner]) for owner in ("f106", "f110", "f111")],
                        ["f106", "f110", "f111"],
                        workspace_root=self.workspace,
                        output=output,
                        report=report,
                    )
                self.assertFalse(output.exists())
                self.assertFalse(report.exists())

    def test_owner_fragment_assembly_never_overwrites_or_leaves_a_partial_pair(self) -> None:
        paths = self.write_owner_fragments(self.owner_fragment_documents(), "no-overwrite")
        fragments = [(owner, paths[owner]) for owner in ("f106", "f110", "f111")]

        existing_report = self.root / "existing-report.json"
        existing_report.write_bytes(b"keep report\n")
        absent_output = self.root / "cleaned-output.json"
        with self.assertRaises(ContractError):
            assemble_registration(
                fragments,
                ["f106", "f110", "f111"],
                workspace_root=self.workspace,
                output=absent_output,
                report=existing_report,
            )
        self.assertFalse(absent_output.exists())
        self.assertEqual(existing_report.read_bytes(), b"keep report\n")

        existing_output = self.root / "existing-output.json"
        existing_output.write_bytes(b"keep output\n")
        absent_report = self.root / "absent-report.json"
        with self.assertRaises(ContractError):
            assemble_registration(
                fragments,
                ["f106", "f110", "f111"],
                workspace_root=self.workspace,
                output=existing_output,
                report=absent_report,
            )
        self.assertEqual(existing_output.read_bytes(), b"keep output\n")
        self.assertFalse(absent_report.exists())

        victim = self.root / "output-symlink-victim.json"
        victim.write_bytes(b"keep victim\n")
        symlink_output = self.root / "output-symlink.json"
        symlink_output.symlink_to(victim)
        symlink_report = self.root / "output-symlink-report.json"
        with self.assertRaises(ContractError):
            assemble_registration(
                fragments,
                ["f106", "f110", "f111"],
                workspace_root=self.workspace,
                output=symlink_output,
                report=symlink_report,
            )
        self.assertTrue(symlink_output.is_symlink())
        self.assertEqual(victim.read_bytes(), b"keep victim\n")
        self.assertFalse(symlink_report.exists())

    def test_staged_dependency_changes_rebuild_the_consumer(self) -> None:
        consumer_repository = self.workspace / "consumer"
        consumer_repository.mkdir()
        git(consumer_repository, "init", "--initial-branch=main")
        license_bytes = b"consumer test license\n"
        (consumer_repository / "LICENSE").write_bytes(license_bytes)
        git(consumer_repository, "add", "LICENSE")
        git(consumer_repository, "commit", "-m", "consumer fixture")
        consumer_commit = git(consumer_repository, "rev-parse", "HEAD")

        document = copy.deepcopy(self.registration_document)
        provider = document["components"][0]
        consumer = copy.deepcopy(provider)
        consumer.update(
            {
                "component_id": "example-consumer",
                "component_version": "2.0.0",
                "expected_commit": consumer_commit,
                "instance_id": "consumer",
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
                "path": "consumer",
                "requested_ref": consumer_commit,
            }
        )
        consumer["build"] = {
            "artifacts": [
                {
                    "artifact_id": "consumer-data",
                    "artifact_kind": "data",
                    "path": "share/consumer/provider-payload.txt",
                }
            ],
            "commands": [
                [
                    "{tool:cp}",
                    "{dependency:provider}/share/provider/payload.txt",
                    "{source}/built.txt",
                ]
            ],
            "copies": [
                {
                    "destination": "share/consumer/provider-payload.txt",
                    "mode": 420,
                    "source": "built.txt",
                }
            ],
            "environment": {},
        }
        document["components"] = [consumer, provider]
        document["dependencies"] = [
            {
                "consumption_mode": "staged-prefix",
                "from": "consumer",
                "required_abi_version": provider["abi_version"],
                "required_api_version": provider["api_version"],
                "required_tests": ["installed-consumer"],
                "runtime_process": "consumer-runtime",
                "to": "provider",
            }
        ]
        cache = self.root / "dependency-cache"
        local_sources = {
            "consumer": consumer_repository,
            "provider": self.repository,
        }

        def qualify_and_stage(
            candidate: dict[str, object], name: str, cache_path: Path = cache
        ):
            registration_path = self.root / f"{name}-registration.json"
            workspace_path = self.root / f"{name}-workspace.json"
            atomic_write_json(registration_path, candidate)
            registration = load_registration(registration_path)
            workspace = emit_workspace_manifest(
                registration,
                workspace_path,
                local_sources=local_sources,
                qualify=True,
            )
            report = stage_workspace(
                registration,
                workspace,
                cache=cache_path,
                destination=self.root / f"{name}-stage",
                release="0.2.1",
                release_lock=self.root / f"{name}.lock.json",
                local_sources=local_sources,
            )
            return report, workspace, load_json(self.root / f"{name}.lock.json")

        missing_reference = copy.deepcopy(document)
        missing_consumer = next(
            item
            for item in missing_reference["components"]
            if item["instance_id"] == "consumer"
        )
        missing_consumer["build"]["commands"] = [
            ["{tool:cp}", "{source}/LICENSE", "{source}/built.txt"]
        ]
        with self.assertRaisesRegex(BuildError, "missing=\\['provider'\\]"):
            qualify_and_stage(
                missing_reference,
                "dependency-missing-reference",
                self.root / "dependency-missing-reference-cache",
            )

        collision = copy.deepcopy(document)
        collision_consumer = next(
            item
            for item in collision["components"]
            if item["instance_id"] == "consumer"
        )
        collision_consumer["build"]["artifacts"][0]["path"] = (
            "share/provider/payload.txt"
        )
        collision_consumer["build"]["copies"][0]["destination"] = (
            "share/provider/payload.txt"
        )
        with self.assertRaisesRegex(BuildError, "duplicate staged artifact path"):
            qualify_and_stage(
                collision,
                "dependency-path-collision",
                self.root / "dependency-path-collision-cache",
            )
        self.assertFalse((self.root / "dependency-path-collision-stage").exists())
        self.assertFalse((self.root / "dependency-path-collision.lock.json").exists())

        first, first_workspace, first_lock = qualify_and_stage(document, "dependency-first")
        self.assertEqual((first.fetches, first.builds), (2, 2))
        first_consumer = next(
            item for item in first_lock["components"] if item["instance_id"] == "consumer"
        )
        workspace_consumer = next(
            item
            for item in first_workspace["components"]
            if item["instance_id"] == "consumer"
        )
        self.assertNotIn(
            "f120_staged_dependencies_sha256", workspace_consumer["build_options"]
        )
        self.assertIn(
            "f120_staged_dependencies_sha256", first_consumer["build_options"]
        )
        first_report = first.evidence_document()
        self.assertEqual(first_report["build_order"], ["provider", "consumer"])
        self.assertEqual(len(first_report["source_receipts"]), 2)
        self.assertEqual(len(first_report["build_receipts"]), 2)
        first_consumer_receipt = next(
            item
            for item in first_report["build_receipts"]
            if item["component_instance"] == "consumer"
        )
        self.assertEqual(
            first_consumer_receipt["staged_dependencies_sha256"],
            first_consumer["build_options"]["f120_staged_dependencies_sha256"],
        )

        (self.repository / "payload.txt").write_bytes(b"changed provider artifact\n")
        git(self.repository, "add", "payload.txt")
        git(self.repository, "commit", "-m", "change provider artifact")
        changed_commit = git(self.repository, "rev-parse", "HEAD")
        changed = copy.deepcopy(document)
        changed_provider = next(
            item for item in changed["components"] if item["instance_id"] == "provider"
        )
        changed_provider["expected_commit"] = changed_commit
        changed_provider["requested_ref"] = changed_commit

        second, _, second_lock = qualify_and_stage(changed, "dependency-second")
        warm, _, warm_lock = qualify_and_stage(changed, "dependency-warm")
        clean, _, clean_lock = qualify_and_stage(
            changed, "dependency-clean", self.root / "dependency-clean-cache"
        )
        self.assertEqual((second.fetches, second.builds), (1, 2))
        self.assertEqual((warm.fetches, warm.builds), (0, 0))
        self.assertEqual((clean.fetches, clean.builds), (2, 2))
        warm_report = warm.evidence_document()
        self.assertEqual(
            sum(item["fetches"] for item in warm_report["source_receipts"]), 0
        )
        self.assertEqual(
            sum(item["fetch_bytes"] for item in warm_report["source_receipts"]), 0
        )
        self.assertEqual(
            sum(item["builds"] for item in warm_report["build_receipts"]), 0
        )
        self.assertTrue(
            all(item["cache_hit"] for item in warm_report["source_receipts"])
        )
        self.assertTrue(
            all(item["cache_hit"] for item in warm_report["build_receipts"])
        )
        second_consumer = next(
            item for item in second_lock["components"] if item["instance_id"] == "consumer"
        )
        self.assertNotEqual(
            first_consumer["build_options"]["f120_staged_dependencies_sha256"],
            second_consumer["build_options"]["f120_staged_dependencies_sha256"],
        )
        first_artifact = next(
            item
            for item in first_lock["artifacts"]
            if item["artifact_id"] == "consumer-data"
        )
        second_artifact = next(
            item
            for item in second_lock["artifacts"]
            if item["artifact_id"] == "consumer-data"
        )
        self.assertNotEqual(
            first_artifact["build_key_sha256"], second_artifact["build_key_sha256"]
        )
        self.assertEqual(second_lock, warm_lock)
        self.assertEqual(second_lock, clean_lock)
        self.assertEqual(
            tree_bytes(self.root / "dependency-second-stage"),
            tree_bytes(self.root / "dependency-warm-stage"),
        )
        self.assertEqual(
            tree_bytes(self.root / "dependency-second-stage"),
            tree_bytes(self.root / "dependency-clean-stage"),
        )
        self.assertEqual(
            (
                self.root
                / "dependency-second-stage/share/consumer/provider-payload.txt"
            ).read_bytes(),
            b"changed provider artifact\n",
        )

        cyclic = copy.deepcopy(document)
        cyclic["dependencies"].append(
            {
                "consumption_mode": "staged-prefix",
                "from": "provider",
                "required_abi_version": consumer["abi_version"],
                "required_api_version": consumer["api_version"],
                "required_tests": ["installed-provider"],
                "runtime_process": "provider-runtime",
                "to": "consumer",
            }
        )
        cyclic_path = self.root / "dependency-cycle-registration.json"
        atomic_write_json(cyclic_path, cyclic)
        with self.assertRaisesRegex(ContractError, "staged-prefix dependency cycle"):
            _staged_build_order(load_registration(cyclic_path))

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

    def test_corrupt_build_entry_is_quarantined_and_rebuilt(self) -> None:
        cache = self.root / "cache"
        cold = self.stage(cache, "stage-one")
        self.assertEqual(cold.builds, 1)
        build_metadata = next((cache / "builds" / "sha256").glob("*/metadata.json"))
        build_metadata.write_text("{}\n", encoding="utf-8")
        recovered = self.stage(cache, "stage-two")
        self.assertEqual((recovered.fetches, recovered.builds), (0, 1))
        self.assertTrue(any((cache / "quarantine" / "builds").iterdir()))

    def test_exact_build_dimensions_separate_real_cache_entries(self) -> None:
        cache = self.root / "dimension-cache"
        cold = self.stage(cache, "dimension-base")
        self.assertEqual((cold.fetches, cold.builds), (1, 1))
        variants = (
            ("architecture", lambda item: item.__setitem__("architecture", "aarch64-linux-gnu")),
            ("features", lambda item: item.__setitem__("features", ["fixture", "variant"])),
            (
                "toolchain",
                lambda item: item["toolchain"].__setitem__("version", "fixture-variant"),
            ),
        )
        for label, mutate in variants:
            with self.subTest(dimension=label):
                document = copy.deepcopy(self.registration_document)
                mutate(document["components"][0])
                registration_path = self.root / f"dimension-{label}.json"
                manifest_path = self.root / f"dimension-{label}-workspace.json"
                atomic_write_json(registration_path, document)
                registration = load_registration(registration_path)
                manifest = emit_workspace_manifest(
                    registration,
                    manifest_path,
                    local_sources={"provider": self.repository},
                    qualify=True,
                )
                report = stage_workspace(
                    registration,
                    manifest,
                    cache=cache,
                    destination=self.root / f"dimension-{label}-stage",
                    release="0.2.1",
                    release_lock=self.root / f"dimension-{label}.lock.json",
                    local_sources={"provider": self.repository},
                )
                self.assertEqual((report.fetches, report.builds), (0, 1))
        self.assertEqual(len(list((cache / "builds" / "sha256").iterdir())), 4)

    def test_same_source_tree_across_commits_reuses_content_keys(self) -> None:
        cache = self.root / "same-tree-cache"
        first = self.stage(cache, "same-tree-first")
        self.assertEqual((first.fetches, first.builds), (1, 1))
        first_source_digest = self.manifest["components"][0]["source_sha256"]

        git(self.repository, "commit", "--allow-empty", "-m", "same tree, new commit")
        second_commit = git(self.repository, "rev-parse", "HEAD")
        document = copy.deepcopy(self.registration_document)
        document["components"][0]["expected_commit"] = second_commit
        document["components"][0]["requested_ref"] = second_commit
        registration_path = self.root / "same-tree-registration.json"
        manifest_path = self.root / "same-tree-workspace.json"
        atomic_write_json(registration_path, document)
        registration = load_registration(registration_path)
        manifest = emit_workspace_manifest(
            registration,
            manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        self.assertEqual(manifest["components"][0]["source_sha256"], first_source_digest)
        second = stage_workspace(
            registration,
            manifest,
            cache=cache,
            destination=self.root / "same-tree-second",
            release="0.2.1",
            release_lock=self.root / "same-tree-second.lock.json",
            local_sources={"provider": self.repository},
        )
        self.assertEqual((second.fetches, second.builds), (0, 0))
        self.assertEqual(
            tree_bytes(self.root / "same-tree-first"),
            tree_bytes(self.root / "same-tree-second"),
        )
        source_metadata = load_json(
            next((cache / "sources" / "sha256").glob("*/metadata.json"))
        )
        build_metadata = load_json(
            next((cache / "builds" / "sha256").glob("*/metadata.json"))
        )
        self.assertNotIn("resolved_commit", source_metadata)
        self.assertNotIn("resolved_commit", build_metadata)

    def test_same_tree_rebuild_is_independent_of_commit_timestamp(self) -> None:
        startup_marker = self.root / "provider-sitecustomize-marker"
        (self.repository / "sitecustomize.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(startup_marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        git(self.repository, "add", "sitecustomize.py")
        git(self.repository, "commit", "-m", "add calibrated provider startup hook")
        first_commit = git(self.repository, "rev-parse", "HEAD")
        writer = self.root / "write-source-epoch"
        writer.write_text(
            "#!/usr/bin/python3\n"
            "import os\n"
            "import pathlib\n"
            "import sys\n"
            "pathlib.Path(sys.argv[1]).write_text("
            "os.environ['SOURCE_DATE_EPOCH'], encoding='utf-8')\n",
            encoding="utf-8",
        )
        writer.chmod(0o755)
        first_document = copy.deepcopy(self.registration_document)
        first_component = first_document["components"][0]
        first_component["expected_commit"] = first_commit
        first_component["requested_ref"] = first_commit
        first_component["toolchain"] = {
            "executables": [
                {
                    "kind": "python-interpreter",
                    "name": "python",
                    "path": str(Path(sys.executable).resolve()),
                    "sha256": file_sha256(Path(sys.executable).resolve()),
                },
                {
                    "interpreter": "python",
                    "kind": "python-script",
                    "name": "write-source-epoch",
                    "path": str(writer),
                    "sha256": file_sha256(writer),
                }
            ],
            "name": "epoch-writer",
            "version": "fixture",
        }
        first_component["build"]["commands"] = [
            ["{tool:write-source-epoch}", "{source}/built.txt"]
        ]
        first_registration_path = self.root / "epoch-first-registration.json"
        first_manifest_path = self.root / "epoch-first-workspace.json"
        atomic_write_json(first_registration_path, first_document)
        first_registration = load_registration(first_registration_path)
        first_manifest = emit_workspace_manifest(
            first_registration,
            first_manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        cache = self.root / "epoch-cache"
        stage_workspace(
            first_registration,
            first_manifest,
            cache=cache,
            destination=self.root / "epoch-first-stage",
            release="0.2.1",
            release_lock=self.root / "epoch-first.lock.json",
            local_sources={"provider": self.repository},
        )
        self.assertFalse(startup_marker.exists())

        git(
            self.repository,
            "commit",
            "--allow-empty",
            "-m",
            "same tree at a different epoch",
            extra_environment={
                "GIT_AUTHOR_DATE": "@2000000000",
                "GIT_COMMITTER_DATE": "@2000000000",
            },
        )
        second_commit = git(self.repository, "rev-parse", "HEAD")
        second_document = copy.deepcopy(first_document)
        second_component = second_document["components"][0]
        second_component["expected_commit"] = second_commit
        second_component["requested_ref"] = second_commit
        second_registration_path = self.root / "epoch-second-registration.json"
        second_manifest_path = self.root / "epoch-second-workspace.json"
        atomic_write_json(second_registration_path, second_document)
        second_registration = load_registration(second_registration_path)
        second_manifest = emit_workspace_manifest(
            second_registration,
            second_manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        self.assertEqual(
            first_manifest["components"][0]["source_sha256"],
            second_manifest["components"][0]["source_sha256"],
        )
        build_key = next((cache / "builds" / "sha256").iterdir()).name
        evict_entry(cache, "builds", build_key)
        rebuilt = stage_workspace(
            second_registration,
            second_manifest,
            cache=cache,
            destination=self.root / "epoch-second-stage",
            release="0.2.1",
            release_lock=self.root / "epoch-second.lock.json",
            local_sources={"provider": self.repository},
        )
        self.assertEqual((rebuilt.fetches, rebuilt.builds), (0, 1))
        self.assertFalse(startup_marker.exists())
        self.assertEqual(
            tree_bytes(self.root / "epoch-first-stage"),
            tree_bytes(self.root / "epoch-second-stage"),
        )
        artifact = self.root / "epoch-second-stage/share/provider/payload.txt"
        self.assertEqual(artifact.read_text(encoding="utf-8"), "0")

    def test_all_frozen_artifact_kinds_are_staged(self) -> None:
        document = copy.deepcopy(self.registration_document)
        kinds = (
            ("provider-command", "command", "bin/provider", 493),
            ("provider-data", "data", "share/provider/data", 420),
            ("provider-header", "header", "include/provider.h", 420),
            ("provider-library", "library", "lib/libprovider.a", 420),
            ("provider-notice", "notice", "share/licenses/provider", 420),
            ("provider-pkg-config", "pkg-config", "lib/pkgconfig/provider.pc", 420),
            (
                "provider-python-package",
                "python-package",
                "lib/python/provider.py",
                420,
            ),
        )
        build = document["components"][0]["build"]
        build["artifacts"] = [
            {"artifact_id": identifier, "artifact_kind": kind, "path": path}
            for identifier, kind, path, _ in kinds
        ]
        build["copies"] = [
            {"destination": path, "mode": mode, "source": "built.txt"}
            for _, _, path, mode in kinds
        ]
        registration_path = self.root / "all-artifacts-registration.json"
        manifest_path = self.root / "all-artifacts-workspace.json"
        lock_path = self.root / "all-artifacts.lock.json"
        atomic_write_json(registration_path, document)
        registration = load_registration(registration_path)
        manifest = emit_workspace_manifest(
            registration,
            manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        stage_workspace(
            registration,
            manifest,
            cache=self.root / "all-artifacts-cache",
            destination=self.root / "all-artifacts-stage",
            release="0.2.1",
            release_lock=lock_path,
            local_sources={"provider": self.repository},
        )
        lock = load_json(lock_path)
        self.assertEqual(
            {item["artifact_kind"] for item in lock["artifacts"]},
            {
                "command",
                "data",
                "header",
                "library",
                "manifest",
                "notice",
                "pkg-config",
                "python-package",
            },
        )

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
                    "kind": "native",
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

    def test_cancelled_source_fetch_publishes_nothing(self) -> None:
        cache = self.root / "cancel-source-cache"
        component = self.manifest["components"][0]
        from kilix_f120 import source_cache

        original_run_git = source_cache.run_git

        def interrupt_fetch(repository, arguments, **keywords):
            if "fetch" in arguments:
                raise KeyboardInterrupt()
            return original_run_git(repository, arguments, **keywords)

        with mock.patch(
            "kilix_f120.source_cache.run_git", side_effect=interrupt_fetch
        ):
            with self.assertRaises(KeyboardInterrupt):
                ensure_source(cache, component, local_source=self.repository)
        self.assertFalse(any((cache / "sources" / "sha256").glob("*")))
        self.assertFalse(any((cache / "tmp" / "sources").glob("candidate-*")))

    def test_failed_lock_publication_retires_published_prefix(self) -> None:
        cache = self.root / "failed-publication-cache"
        prefix = self.root / "failed-publication-stage"
        lock = self.root / "failed-publication.lock.json"
        with mock.patch(
            "kilix_f120.stage._publish_lock",
            side_effect=BuildError("injected lock publication failure"),
        ):
            with self.assertRaises(BuildError):
                stage_workspace(
                    self.registration,
                    self.manifest,
                    cache=cache,
                    destination=prefix,
                    release="0.2.1",
                    release_lock=lock,
                    local_sources={"provider": self.repository},
                )
        self.assertFalse(prefix.exists())
        self.assertFalse(lock.exists())
        failed = self.root / ".kilix-f120-failed"
        self.assertEqual(len(list(failed.iterdir())), 1)

    def test_stage_publication_race_does_not_replace_destination(self) -> None:
        cache = self.root / "raced-publication-cache"
        prefix = self.root / "raced-publication-stage"
        lock = self.root / "raced-publication.lock.json"
        from kilix_f120 import stage as stage_module

        rename_no_replace = stage_module.rename_directory_no_replace

        def inject_competing_destination(candidate, destination):
            destination.mkdir()
            (destination / "owner-data.txt").write_text(
                "must survive\n", encoding="utf-8"
            )
            rename_no_replace(candidate, destination)

        with mock.patch.object(
            stage_module,
            "rename_directory_no_replace",
            side_effect=inject_competing_destination,
        ):
            with self.assertRaises(BuildError):
                stage_workspace(
                    self.registration,
                    self.manifest,
                    cache=cache,
                    destination=prefix,
                    release="0.2.1",
                    release_lock=lock,
                    local_sources={"provider": self.repository},
                )
        self.assertEqual(
            (prefix / "owner-data.txt").read_text(encoding="utf-8"),
            "must survive\n",
        )
        self.assertFalse(lock.exists())

    def test_cache_and_prefix_must_be_outside_workspace(self) -> None:
        with self.assertRaises(BuildError):
            stage_workspace(
                self.registration,
                self.manifest,
                cache=self.workspace / "cache",
                destination=self.root / "outside-stage",
                release="0.2.1",
                release_lock=self.root / "outside.lock.json",
                local_sources={"provider": self.repository},
            )
        with self.assertRaises(BuildError):
            stage_workspace(
                self.registration,
                self.manifest,
                cache=self.root / "outside-cache",
                destination=self.workspace / "stage",
                release="0.2.1",
                release_lock=self.root / "inside.lock.json",
                local_sources={"provider": self.repository},
            )

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

    def test_stage_retirement_refuses_an_arbitrary_directory(self) -> None:
        arbitrary = self.root / "not-a-stage"
        arbitrary.mkdir()
        (arbitrary / "important.txt").write_text("keep\n", encoding="utf-8")
        with self.assertRaises(BuildError):
            retire_stage(arbitrary)
        self.assertEqual(
            (arbitrary / "important.txt").read_text(encoding="utf-8"), "keep\n"
        )

    def test_registration_rejects_reserved_build_environment(self) -> None:
        for index, name in enumerate(("HOME", "PYTHONPATH", "LD_PRELOAD", "UV_PROJECT")):
            with self.subTest(name=name):
                document = copy.deepcopy(self.registration_document)
                document["components"][0]["build"]["environment"] = {name: "/tmp"}
                path = self.root / f"reserved-environment-{index}.json"
                atomic_write_json(path, document)
                with self.assertRaises(RegistrationError):
                    load_registration(path)
        allowed = copy.deepcopy(self.registration_document)
        allowed["components"][0]["build"]["environment"] = {
            "F120_INPUT_MODE": "fixture"
        }
        allowed_path = self.root / "allowed-environment.json"
        atomic_write_json(allowed_path, allowed)
        self.assertEqual(
            load_registration(allowed_path).components[0].build.environment,
            (("F120_INPUT_MODE", "fixture"),),
        )

    def test_registration_rejects_reserved_derived_build_options(self) -> None:
        for index, name in enumerate(
            ("f120_recipe_sha256", "f120_staged_dependencies_sha256")
        ):
            with self.subTest(name=name):
                document = copy.deepcopy(self.registration_document)
                document["components"][0]["build_options"] = {name: "0" * 64}
                path = self.root / f"reserved-build-option-{index}.json"
                atomic_write_json(path, document)
                with self.assertRaises(RegistrationError):
                    load_registration(path)

    def test_build_recipe_refuses_an_unbound_host_path(self) -> None:
        document = copy.deepcopy(self.registration_document)
        document["components"][0]["build"]["commands"][0].append("/tmp/host-input")
        registration_path = self.root / "host-path-registration.json"
        manifest_path = self.root / "host-path-workspace.json"
        atomic_write_json(registration_path, document)
        registration = load_registration(registration_path)
        manifest = emit_workspace_manifest(
            registration,
            manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        with self.assertRaisesRegex(BuildError, "unbound path"):
            stage_workspace(
                registration,
                manifest,
                cache=self.root / "host-path-cache",
                destination=self.root / "host-path-stage",
                release="0.2.1",
                release_lock=self.root / "host-path.lock.json",
                local_sources={"provider": self.repository},
            )
        self.assertFalse((self.root / "host-path-stage").exists())
        self.assertFalse((self.root / "host-path.lock.json").exists())

    def test_build_recipe_refuses_an_undeclared_dependency(self) -> None:
        document = copy.deepcopy(self.registration_document)
        document["components"][0]["build"]["commands"][0][1] = (
            "{dependency:undeclared}/share/provider/payload.txt"
        )
        registration_path = self.root / "undeclared-dependency-registration.json"
        manifest_path = self.root / "undeclared-dependency-workspace.json"
        atomic_write_json(registration_path, document)
        registration = load_registration(registration_path)
        manifest = emit_workspace_manifest(
            registration,
            manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        with self.assertRaisesRegex(
            BuildError, "undeclared=\\['undeclared'\\]"
        ):
            stage_workspace(
                registration,
                manifest,
                cache=self.root / "undeclared-dependency-cache",
                destination=self.root / "undeclared-dependency-stage",
                release="0.2.1",
                release_lock=self.root / "undeclared-dependency.lock.json",
                local_sources={"provider": self.repository},
            )
        self.assertFalse((self.root / "undeclared-dependency-stage").exists())
        self.assertFalse((self.root / "undeclared-dependency.lock.json").exists())

    def test_registration_v1_is_refused_not_reinterpreted(self) -> None:
        document = copy.deepcopy(self.registration_document)
        document["schema"] = "kilix.f120.registration/v1"
        path = self.root / "registration-v1.json"
        atomic_write_json(path, document)
        with self.assertRaises(RegistrationError):
            load_registration(path)

    def test_registered_wrapper_cannot_exec_an_undeclared_python(self) -> None:
        marker = self.root / "undeclared-python-marker"
        (self.repository / "sitecustomize.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        git(self.repository, "add", "sitecustomize.py")
        git(self.repository, "commit", "-m", "add wrapper startup probe")
        commit = git(self.repository, "rev-parse", "HEAD")
        shell = Path("/bin/sh").resolve()
        python = Path("/usr/bin/python3").resolve()
        wrapper = self.root / "python-wrapper"
        wrapper.write_text(
            f"#!{shell}\nPYTHONPATH=: exec {python} -c 'raise SystemExit(0)'\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        document = copy.deepcopy(self.registration_document)
        component = document["components"][0]
        component["expected_commit"] = commit
        component["requested_ref"] = commit
        component["toolchain"] = {
            "executables": [
                {
                    "kind": "native",
                    "name": "sh",
                    "path": str(shell),
                    "sha256": file_sha256(shell),
                },
                {
                    "interpreter": "sh",
                    "kind": "script",
                    "name": "wrapper",
                    "path": str(wrapper),
                    "sha256": file_sha256(wrapper),
                },
            ],
            "name": "wrapper-fixture",
            "version": "fixture",
        }
        component["build"]["commands"] = [["{tool:wrapper}"]]
        registration_path = self.root / "wrapper-registration.json"
        manifest_path = self.root / "wrapper-workspace.json"
        atomic_write_json(registration_path, document)
        registration = load_registration(registration_path)
        manifest = emit_workspace_manifest(
            registration,
            manifest_path,
            local_sources={"provider": self.repository},
            qualify=True,
        )
        with self.assertRaises(BuildError):
            stage_workspace(
                registration,
                manifest,
                cache=self.root / "wrapper-cache",
                destination=self.root / "wrapper-stage",
                release="0.2.1",
                release_lock=self.root / "wrapper.lock.json",
                local_sources={"provider": self.repository},
            )
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / "wrapper-stage").exists())
        self.assertFalse((self.root / "wrapper.lock.json").exists())

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

    def test_frozen_files_are_checked_before_validator_execution(self) -> None:
        def substituted_digest(path: Path) -> str:
            if path.name == "validate_f120.py":
                return "0" * 64
            return file_sha256(path)

        with mock.patch(
            "kilix_f120.contracts.file_sha256", side_effect=substituted_digest
        ):
            with self.assertRaises(ContractError):
                verify_contract_package()

    def test_nonfinite_json_and_uppercase_host_are_rejected(self) -> None:
        with self.assertRaises(ContractError):
            canonical_bytes({"not_finite": float("nan")})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nonfinite.json"
            path.write_text('{"not_finite": NaN}\n', encoding="utf-8")
            with self.assertRaises(ContractError):
                load_json(path)
        with self.assertRaises(GitError):
            canonical_https_url("https://EXAMPLE.com/provider.git")

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
