"""The unselected ARM64 0.2.2 closure stays refused and leaves AMD64 selected.

The candidate replaces every architecture-bound AMD64 value with a recorded
ARM64 input or names it as unresolved. A rendered companion is complete enough
for the selector's closure checks, so these fixtures prove the remaining
refusal is the explicit admission boundary rather than a missing file.
"""

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_amd64_only_inputs as inputs
import test_closure_selection as selection


ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "build/verify-arm64-closure-candidate.py"
spec = importlib.util.spec_from_file_location("arm64_closure_candidate", VERIFIER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

AMD64_QT = "623b5f2669fbf42679694ca5c8d3f841536a1f2bc449d66166f057650c8f4ad1"
ARM64_QT = "87c997c7bad3fa304b2de829d2696d67749ad646bb408e011e335f7170d02b80"
# Fixture-only stand-ins for the unresolved carrier; no ARM64 carrier exists.
FIXTURE_CARRIER = {
    "PLEBIAN_OS_VOICE_CARRIER_DIR": "releases/0.2.2-arm64-model-compliance",
    "PLEBIAN_OS_VOICE_CARRIER_SHA256": "e" * 64,
    "PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256": "f" * 64,
}
# The only Waydroid form the selector accepts on ARM64 today.
FIXTURE_WAYDROID = {
    "PLEBIAN_OS_INSTALL_WAYDROID": "0",
    "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256": "",
}


def load():
    return json.loads(module.CANDIDATE.read_text())


def companion(candidate=None):
    """Rendered companion text with fixture values in the unresolved keys."""
    candidate = load() if candidate is None else candidate
    amd64, requirements = module.validate(candidate)
    env, req = module.render(candidate, amd64, requirements)
    fill = {**FIXTURE_CARRIER, **FIXTURE_WAYDROID}
    env += "".join(f"{k}={v}\n" for k, v in fill.items())
    req += "".join(f"{k}={v}\n" for k, v in fill.items() if k in requirements)
    return env, req


def selected_values(candidate):
    values = {}
    for entry in candidate["selected"]:
        values.update(entry.get("confirmed", {}))
        values.update(entry["values"])
    return values


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.candidate = load()

    def test_candidate_verifies_unselected_and_admission_refuses(self):
        module.validate(self.candidate)
        blockers = module.admission_blockers(self.candidate)
        for gate in module.GATES:
            self.assertIn(f"open gate: {gate}", blockers)
        self.assertTrue(any(b.startswith("unresolved voice-carrier") for b in blockers))
        self.assertTrue(any(b.startswith("unresolved waydroid") for b in blockers))
        for path in self.candidate["companion"].values():
            self.assertFalse((ROOT / path).exists())

    def test_foreign_or_unproven_candidate_fields_refuse(self):
        qt = next(e for e in self.candidate["selected"] if e["component"] == "qt-runtime")
        mutations = (
            lambda c: c.update(selection="selected"),
            lambda c: c.update(admission="open"),
            lambda c: c["selected"][1]["values"].update(PLEBIAN_OS_QT_RUNTIME_SHA256=AMD64_QT),
            lambda c: c["selected"][2]["values"].update(
                PLEBIAN_OS_MPV_URL=qt["values"]["PLEBIAN_OS_QT_RUNTIME_URL"]),
            lambda c: c["selected"][2]["artifact"].update(
                url=c["selected"][2]["artifact"]["url"].replace("arm64", "amd64")),
            lambda c: c["selected"][1]["artifact"].update(bytes=1),
            lambda c: c["selected"][2]["confirmed"].update(PLEBIAN_OS_MPV_SOURCE_REF="0" * 40),
            lambda c: c["selected"][0]["values"].pop("PLEBIAN_OS_NETINST_SHA256"),
            lambda c: c["unresolved"].pop(),
            lambda c: c["unresolved"][0]["keys"].pop(),
            lambda c: c["neutral_requirements"].update(PLEBIAN_OS_INSTALL_WAYDROID="assumed"),
            lambda c: c["android"].update(selected=True),
            lambda c: c["android"]["system_image"].update(bytes_verified=True),
            lambda c: c["android"]["vendor_image"].update(
                filename="lineage-20.0-20260428-MAINLINE-waydroid_x86_64-vendor.zip"),
            lambda c: c["android"]["packages"][1].update(
                url="https://repo.waydro.id/dists/trixie/libglibutil_1.0.80_amd64.deb"),
            lambda c: c["android"]["binder"].update(devices="binder"),
            lambda c: c["gates"].pop(),
            lambda c: c["gates"][0].update(status="passed"),
            lambda c: c["gates"][0].update(evidence={"path": "x", "sha256": "0" * 64}),
            lambda c: c["runtime_candidate"].update(sha256="0" * 64),
            lambda c: c["preserved_amd64"].pop("releases/0.2.2.env"),
        )
        for index, mutate in enumerate(mutations):
            candidate = copy.deepcopy(self.candidate)
            mutate(candidate)
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                module.validate(candidate)

    def test_passed_gates_need_present_unaltered_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / "evidence.json"
            record.write_text("{}\n")
            candidate = copy.deepcopy(self.candidate)
            candidate["gates"][0].update(status="passed", evidence={
                "path": "evidence.json",
                "sha256": hashlib.sha256(b"{}\n").hexdigest()})
            self.assertNotIn("open gate: arm-closure-review",
                             module.admission_blockers(candidate, root))
            record.write_text("{\"altered\": true}\n")
            self.assertIn("gate arm-closure-review evidence is absent or altered",
                          module.admission_blockers(candidate, root))
            candidate["gates"][0]["evidence"]["path"] = "../outside.json"
            self.assertIn("gate arm-closure-review evidence is absent or altered",
                          module.admission_blockers(candidate, root))

    def test_selected_amd64_files_and_companion_absence_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in [*self.candidate["preserved_amd64"],
                         self.candidate["runtime_candidate"]["path"]]:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, root / path)
            module.validate(self.candidate, root)
            (root / "releases/0.2.2-arm64.env").write_text("PLEBIAN_OS_VERSION=0.2.2\n")
            with self.assertRaisesRegex(ValueError, "exists although"):
                module.validate(self.candidate, root)
            (root / "releases/0.2.2-arm64.env").unlink()
            with (root / "releases/0.2.2.env").open("a") as stream:
                stream.write("# drift\n")
            with self.assertRaisesRegex(ValueError, "selected AMD64 file changed"):
                module.validate(self.candidate, root)

    def test_render_replaces_every_bound_value_and_omits_unresolved(self):
        amd64, requirements = module.validate(self.candidate)
        env, req = module.render(self.candidate, amd64, requirements)
        rendered = module.read_env(Path(self._write(env)))
        unresolved = {k for e in self.candidate["unresolved"] for k in e["keys"]}
        self.assertEqual(set(rendered), set(amd64) - unresolved)
        values = selected_values(self.candidate)
        for key in module.ARCHITECTURE_BOUND:
            if key in unresolved:
                continue
            self.assertEqual(rendered[key], values[key])
            if key not in self.candidate_confirmed():
                self.assertNotEqual(rendered[key], amd64[key], key)
        for key, value in rendered.items():
            self.assertIsNone(module.FOREIGN.search(value), key)
        self.assertEqual(rendered["PLEBIAN_OS_QT_RUNTIME_SHA256"], ARM64_QT)
        self.assertIn("UNSELECTED CANDIDATE", req)
        self.assertEqual(amd64["PLEBIAN_OS_QT_RUNTIME_SHA256"], AMD64_QT)

    def candidate_confirmed(self):
        return {k for e in self.candidate["selected"] for k in e.get("confirmed", {})}

    def _write(self, text):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        path = Path(directory) / "companion.env"
        path.write_text(text)
        return path

    def test_render_refuses_the_source_tree(self):
        result = subprocess.run(
            ["python3", str(VERIFIER), "render", "--out", str(ROOT / "releases")],
            capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the source tree", result.stderr)
        self.assertFalse((ROOT / "releases/0.2.2-arm64.env").exists())


class SelectorBoundaryTests(unittest.TestCase):
    """Run the real selector against a tag carrying the rendered companion."""

    def setUp(self):
        self.fixture = selection.ClosureSelectionTests(
            "test_arm64_sidecar_is_read_but_amd64_waydroid_still_refuses")
        self.env_text, self.requirements_text = companion()

    def _tag(self, base):
        env_file = self.fixture._machine(base)
        self.fixture._source(
            base, manifest_text=(ROOT / "releases/0.2.2.env").read_text(),
            version="0.2.2", release="0.2.2", tag="v0.2.2",
            arm64_manifest_text=self.env_text,
            arm64_requirements_text=self.requirements_text)
        return env_file

    @staticmethod
    def _machine_type(base, machine):
        bindir = base / "bin"
        bindir.mkdir()
        uname = bindir / "uname"
        uname.write_text(f"#!/bin/sh\necho {machine}\n")
        uname.chmod(0o755)
        return {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}

    def test_complete_arm64_companion_is_refused_before_any_write(self):
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                env_file = self._tag(base)
                before = env_file.read_bytes()
                args = ["0.2.2", "--source", str(base / "src"), "--offline"]
                if dry_run:
                    args.append("--dry-run")
                result = self.fixture._run(base, *args, env_extra=self._machine_type(base, "aarch64"))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("0.2.2 ARM64 release admission is closed", result.stderr)
                self.assertIn("releases/0.2.2-arm64.env passed closure checks", result.stderr)
                self.assertNotIn("selectable", result.stdout)
                self.assertEqual(env_file.read_bytes(), before)
                self.assertEqual(list((base / "root/usr/local/bin").iterdir()), [])
                self.assertFalse((base / "root/etc/pleb/closure.env").exists())

    def test_amd64_machine_selects_amd64_values_beside_the_companion(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            env_file = self._tag(base)
            result = self.fixture._run(
                base, "0.2.2", "--source", str(base / "src"), "--offline",
                env_extra=self._machine_type(base, "x86_64"))
            self.assertEqual(result.returncode, 0, result.stderr)
            closure = base / "root/etc/pleb/closure.env"
            written = (closure if closure.exists() else env_file).read_text()
            self.assertIn(AMD64_QT, written)
            self.assertNotIn(ARM64_QT, written)
            self.assertIn("releases/0.2.2.env", result.stdout)
            self.assertNotIn("0.2.2-arm64.env", result.stdout)


class ProvisionBoundaryTests(unittest.TestCase):
    """The provisioner and updater keep the early refusal for ARM64 values."""

    def setUp(self):
        self.fixture = inputs.Amd64OnlyInputTests("test_amd64_keeps_every_release_input")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_arm64_candidate_values_still_refuse_release(self):
        values = selected_values(load())
        arm64 = {key: values[key] for key in (
            "KILIX_PREBUILT_VERSION", "KILIX_PREBUILT_SHA256", "KILIX_VOICE_LIB_URL",
            "PLEBIAN_OS_MPV_URL", "PLEBIAN_OS_NATIVE_DEB_URL",
            "PLEBIAN_OS_QT_RUNTIME_SHA256")}
        provision = {"INSTALL_WAYDROID": "0", "INSTALL_VOICE_MODEL": "1"}
        update = {"PLEBIAN_OS_INSTALL_WAYDROID": "0", "PLEBIAN_OS_INSTALL_VOICE_MODEL": "1"}
        for invoke, flags in ((self.fixture.provision, provision),
                              (self.fixture.update, update)):
            with self.subTest(invoke=invoke.__name__):
                self.fixture.assert_refused(
                    invoke("aarch64", PLEBIAN_OS_RELEASE="0.2.2", **flags, **arm64),
                    "no source-qualified ARM64 closure")
                # The values themselves carry no AMD64 marker the guard knows.
                self.fixture.assert_accepted(
                    invoke("aarch64", PLEBIAN_OS_VERSION="0.2.1", **flags, **arm64))


if __name__ == "__main__":
    unittest.main()
