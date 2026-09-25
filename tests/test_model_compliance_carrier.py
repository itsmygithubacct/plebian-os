"""The release model compliance carrier: acceptance lines AC-1..AC-12.

The carrier (releases/<version>-model-compliance) is what lets a release
advertise speech models while build/remaster-iso.sh keeps F107-A's fail-closed
refusal for every input without it (OD-BA). Each acceptance line below is one
test; AC-11 plants each defect of F100-CARRIER-DESIGN.md §6 and requires the
validator to refuse it for its own reason.

AC-1, AC-3 and AC-4 read kilix-content at PLEBIAN_OS_NATIVE_CONTENT_REF and
kilix-license at KILIX_LICENSE_REF from sibling checkouts (CI fetches exactly
those commits), or from PLEBIAN_OS_KILIX_CONTENT_REPO / PLEBIAN_OS_KILIX_LICENSE_REPO.
A missing checkout is a failure, never a skip: an unprovable binding is worth
exactly as much as an absent one.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_voice_release_contract as voice_contract  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text().strip()
CARRIER = ROOT / "releases" / f"{VERSION}-model-compliance"
GENERATOR = ROOT / "build" / "generate-model-compliance.py"
REFUSAL = (f"Plebian-OS {VERSION} release mode refuses "
           "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 until an accepted F100 "
           "compliance-carrier interface and receipt are present\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(name: str) -> dict[str, str]:
    values = {}
    for line in (ROOT / "releases" / name).read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def carrier_env(root: Path = CARRIER) -> dict[str, str]:
    return dict(line.split("=", 1) for line in
                (root / "CARRIER.env").read_text().splitlines())


def repo_holding(env_var: str, name: str, commit: str) -> Path | None:
    return voice_contract.repo_holding(
        voice_contract._repo_candidates(env_var, (name,)), commit)


def release_env(carrier: Path = CARRIER, **overrides: str) -> dict[str, str]:
    pins = manifest(f"{VERSION}.env")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    for key in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_RELEASE_MODE",
                "PLEBIAN_OS_INSTALL_VOICE_MODEL", "KILIX_VOICE_REF",
                "KILIX_VOICE_LIB_VERSION", "KILIX_VOICE_LIB_URL",
                "KILIX_VOICE_LIB_SHA256", "KILIX_VOICE_MODEL_URL",
                "KILIX_VOICE_MODEL_SHA256", "PLEBIAN_OS_NATIVE_CONTENT_REF",
                "KILIX_LICENSE_REF", "PLEBIAN_OS_VOICE_CARRIER_SHA256",
                "PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256"):
        env[key] = pins[key]
    env["PLEBIAN_OS_VOICE_CARRIER_DIR"] = str(carrier)
    env.update(overrides)
    return env


def run_guard(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", "set -u\n" + voice_contract._voice_validator_source()
         + "\nvalidate_voice_release_closure"],
        env=env, text=True, capture_output=True)


def regenerate(content: Path, license_: Path, out: Path,
               source: Path = CARRIER) -> subprocess.CompletedProcess:
    args = [sys.executable, str(GENERATOR), "--content-repo", str(content),
            "--license-repo", str(license_), "--out", str(out)]
    for determination in sorted((source / "determinations").glob("*/*")):
        args += ["--determination", f"{determination.parent.name}={determination}"]
    for seat in sorted((source / "seats").glob("*")):
        args += ["--seat", str(seat)]
    return subprocess.run(args, text=True, capture_output=True)


class ModelComplianceCarrierTests(unittest.TestCase):
    def pinned_checkouts(self) -> tuple[Path, Path]:
        pins = manifest(f"{VERSION}.env")
        content = repo_holding("PLEBIAN_OS_KILIX_CONTENT_REPO", "kilix-content",
                               pins["PLEBIAN_OS_NATIVE_CONTENT_REF"])
        license_ = repo_holding("PLEBIAN_OS_KILIX_LICENSE_REPO", "kilix-license",
                                pins["KILIX_LICENSE_REF"])
        self.assertIsNotNone(content, "no kilix-content checkout holds "
                             "PLEBIAN_OS_NATIVE_CONTENT_REF; set PLEBIAN_OS_KILIX_CONTENT_REPO")
        self.assertIsNotNone(license_, "no kilix-license checkout holds "
                             "KILIX_LICENSE_REF; set PLEBIAN_OS_KILIX_LICENSE_REPO")
        return content, license_

    # AC-1
    def test_carrier_regenerates_byte_identically(self):
        content, license_ = self.pinned_checkouts()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "carrier"
            result = regenerate(content, license_, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            produced = {str(p.relative_to(out)): p.read_bytes()
                        for p in out.rglob("*") if p.is_file()}
            committed = {str(p.relative_to(CARRIER)): p.read_bytes()
                         for p in CARRIER.rglob("*") if p.is_file()}
            self.assertEqual(sorted(produced), sorted(committed))
            for name in committed:
                self.assertEqual(produced[name], committed[name], name)

    # AC-2
    def test_carrier_env_is_a_faithful_projection_of_carrier_json(self):
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        env = carrier_env()
        for key in ("schema", "release_id", "dictation_model", "library_wheel_url",
                    "library_wheel_sha256", "interface_content_ref",
                    "interface_content_schema_sha256", "interface_licence_ref",
                    "voice_ref"):
            self.assertEqual(env[key], carrier[key], key)
        self.assertEqual(env["models"].split(), carrier["model_order"])
        self.assertEqual(set(carrier["model_order"]), set(carrier["models"]))
        expected = 10
        for model, entry in carrier["models"].items():
            prefix = "m_" + re.sub(r"[^a-z0-9]", "_", model) + "_"
            projected = {
                "artifact_id": entry["artifact_id"],
                "source_url": entry["source_url"],
                "upstream_host": entry["upstream_host"],
                "manifest_digest": entry["manifest_digest"],
                "artifact_record_sha256": entry["artifact_record_sha256"],
                "licence_record_digest": entry["licence_record_digest"],
                "licence_text_sha256s": " ".join(entry["licence_text_sha256s"]),
                "licensors": "; ".join(entry["licensors"]),
                "decision": entry["decision"],
                "delivery": entry["delivery"],
                "runnable": "yes" if entry["runnable"] else "no",
            }
            if "archive_sha256" in entry:
                projected["archive_sha256"] = entry["archive_sha256"]
                projected["archive_bytes"] = str(entry["archive_bytes"])
            for field, value in projected.items():
                self.assertEqual(env[prefix + field], value, prefix + field)
            expected += len(projected)
        self.assertEqual(len(env), expected, "CARRIER.env has keys CARRIER.json lacks")

    # AC-3
    def test_carrier_licence_records_match_kilix_license(self):
        _, license_ = self.pinned_checkouts()
        ref = manifest(f"{VERSION}.env")["KILIX_LICENSE_REF"]
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        for model, entry in carrier["models"].items():
            upstream = subprocess.run(
                ["git", "-C", str(license_), "--no-replace-objects", "show",
                 f"{ref}:src/kilix_license/data/records/{model}.json"],
                capture_output=True, check=True).stdout
            self.assertEqual((CARRIER / model / "LICENCE-RECORD.json").read_bytes(),
                             upstream, model)
            self.assertEqual(entry["licence_record_file_sha256"], sha256(upstream))

    # AC-4
    def test_carrier_artifact_records_match_kilix_content(self):
        content, _ = self.pinned_checkouts()
        ref = manifest(f"{VERSION}.env")["PLEBIAN_OS_NATIVE_CONTENT_REF"]
        catalog = json.loads(subprocess.run(
            ["git", "-C", str(content), "--no-replace-objects", "show",
             f"{ref}:src/kilix_content/catalog/plebian.json"],
            capture_output=True, check=True).stdout)
        by_id = {asset["id"]: asset for asset in catalog["assets"]}
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        for model, entry in carrier["models"].items():
            artifact = json.loads((CARRIER / model / "ARTIFACT.json").read_bytes())
            self.assertEqual(artifact, by_id[entry["artifact_id"]], model)
            self.assertIn(entry["licence_record_digest"],
                          [item["record_digest"] for item in artifact["licenses"]])
        dictation = carrier["models"][carrier["dictation_model"]]
        self.assertEqual(dictation["archive_sha256"],
                         manifest(f"{VERSION}.env")["KILIX_VOICE_MODEL_SHA256"])

    # AC-5
    def test_carrier_covers_every_advertised_model(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        block = provision[provision.index("validate_voice_model_catalog() {"):]
        block = block[:block.index("\n}\n")]
        advertised = re.findall(r'\(\s*"([a-z0-9.-]+)", "[a-z]+", (True|False),', block)
        self.assertEqual(len(advertised), 3)
        self.assertEqual(carrier_env()["models"].split(), [name for name, _ in advertised])
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        for name, flag in advertised:
            self.assertEqual(carrier["models"][name]["runnable"], flag == "True", name)

    # AC-6
    def test_acceptance_receipt_names_the_real_determinations(self):
        receipt = json.loads((CARRIER / "ACCEPTANCE.json").read_bytes())
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        self.assertEqual(receipt["carrier_sha256"], sha256((CARRIER / "CARRIER.json").read_bytes()))
        covered = set()
        for item in receipt["determinations"]:
            path = CARRIER / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(sha256(path.read_bytes()), item["sha256"], item["path"])
            text = path.read_text()
            self.assertIn("Determined by | The owner", text, item["path"])
            covered.add(item["model"])
        self.assertEqual(covered, set(carrier["models"]))

    # AC-7
    def test_acceptance_receipt_names_two_independent_seats(self):
        receipt = json.loads((CARRIER / "ACCEPTANCE.json").read_bytes())
        self.assertEqual(len(receipt["seats"]), 2)
        self.assertEqual(len({seat["sha256"] for seat in receipt["seats"]}), 2)
        for seat in receipt["seats"]:
            path = CARRIER / seat["path"]
            self.assertEqual(sha256(path.read_bytes()), seat["sha256"], seat["path"])
            text = path.read_text()
            self.assertRegex(text, r"(?i)did not author")
            self.assertRegex(text, r"(?m)^VERDICT: ship( with known issues)?\s*$")

    # AC-8
    def test_delivery_statement_is_true_of_this_image(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("readonly PROVISION_VOICE_WEIGHTS=0", provision)
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        # The download is digest-verified: the first-use flow is in the content
        # the release pins, and kilix-voice gates the weights on a receipt.
        pins = manifest(f"{VERSION}.env")
        self.assertIsNone(voice_contract.content_chain_gap(pins["KILIX_REF"]))
        self.assertIsNone(voice_contract.receipt_gate_gap(pins["KILIX_VOICE_REF"]))
        for model, entry in carrier["models"].items():
            delivery = (CARRIER / model / "DELIVERY").read_text()
            self.assertIn("No model weights are present in this image, and "
                          "provisioning downloads none.", delivery)
            self.assertIn(f"require_covering_receipt, kilix-voice {pins['KILIX_VOICE_REF']}",
                          delivery)
            self.assertEqual("not runnable" in delivery, not entry["runnable"], model)

    # AC-9
    def test_guard_refuses_without_a_carrier(self):
        for overrides in ({"PLEBIAN_OS_VOICE_CARRIER_DIR": ""},
                          {"PLEBIAN_OS_VOICE_CARRIER_DIR": "",
                           "PLEBIAN_OS_VOICE_CARRIER_SHA256": ""}):
            result = run_guard(release_env(**overrides))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, REFUSAL)

    # AC-10
    def test_guard_accepts_the_verified_carrier(self):
        result = run_guard(release_env())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    # AC-11
    def test_guard_refuses_every_planted_carrier_defect(self):
        def resum(root: Path) -> None:
            names = sorted(str(p.relative_to(root)) for p in root.rglob("*")
                           if p.is_file() and p.name != "SHA256SUMS")
            (root / "SHA256SUMS").write_text("".join(
                f"{sha256((root / n).read_bytes())}  {n}\n" for n in names))

        def edit_env(root: Path, key: str, value: str) -> None:
            lines = (root / "CARRIER.env").read_text().splitlines()
            lines = [f"{key}={value}" if line.startswith(f"{key}=") else line
                     for line in lines]
            (root / "CARRIER.env").write_text("\n".join(lines) + "\n")

        dictation = "m_" + re.sub(r"[^a-z0-9]", "_", carrier_env()["dictation_model"])
        text = carrier_env()[f"{dictation}_licence_text_sha256s"].split()[0]

        def empty(root): shutil.rmtree(root); root.mkdir()
        def forged_receipt(root):
            (root / "ACCEPTANCE.json").write_text('{"seats":["fictitious"]}\n'); resum(root)
        def wrong_release(root): edit_env(root, "release_id", "0.2.1"); resum(root)
        def wrong_archive(root):
            value = carrier_env(root)[f"{dictation}_archive_sha256"]
            edit_env(root, f"{dictation}_archive_sha256", ("0" if value[0] != "0" else "1") + value[1:])
            resum(root)
        def borrowed_text(root):
            path = root / "licence-texts" / f"{text}.txt"
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n")); resum(root)
        def unlisted(root): (root / "EXTRA").write_text("x\n")
        def placeholder(root): edit_env(root, f"{dictation}_licensors", "REPLACE_ME"); resum(root)
        def unknown_key(root):
            with open(root / "CARRIER.env", "a") as fh: fh.write("sneaky=1\n")
            resum(root)
        def missing_notice(root): (root / carrier_env()["dictation_model"] / "NOTICE").unlink(); resum(root)
        def other_content(root): edit_env(root, "interface_content_ref", "f" * 40); resum(root)
        def undelivered(root): edit_env(root, f"{dictation}_delivery", "provisioned"); resum(root)

        cases = [
            ("D2 empty carrier", empty, {}, "CARRIER.json is missing"),
            ("D3 forged receipt", forged_receipt, {}, "does not match PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256"),
            ("D3b consistently forged receipt", forged_receipt,
             {"PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256": None}, "is not the receipt for this carrier"),
            ("D4 wrong release", wrong_release, {}, "carrier is for release 0.2.1"),
            ("D5 bound digest differs", wrong_archive, {}, "is not KILIX_VOICE_MODEL_URL/SHA256"),
            ("D7 borrowed licence text", borrowed_text, {}, "is missing or altered"),
            ("D8 unlisted extra file", unlisted, {}, "not listed in SHA256SUMS"),
            ("D11 placeholder value", placeholder, {}, "is empty or a placeholder"),
            ("unknown key", unknown_key, {}, "unknown key sneaky"),
            ("missing notice", missing_notice, {}, "NOTICE is missing"),
            ("other content interface", other_content, {}, "producing interfaces"),
            ("false delivery mode", undelivered, {}, "delivery is not first-use-upstream-download"),
            ("tampered listing", lambda root: (root / "CARRIER.env").write_text(
                (root / "CARRIER.env").read_text() + "\n"), {}, "SHA256SUMS does not verify"),
        ]
        for label, plant, overrides, reason in cases:
            with self.subTest(defect=label), tempfile.TemporaryDirectory() as td:
                root = Path(td) / "carrier"
                shutil.copytree(CARRIER, root)
                plant(root)
                env = release_env(root)
                for key, value in overrides.items():
                    env[key] = sha256((root / "ACCEPTANCE.json").read_bytes()) if value is None else value
                result = run_guard(env)
                self.assertEqual(result.returncode, 1, label)
                self.assertIn(reason, result.stderr, label)
                self.assertTrue(result.stderr.endswith(REFUSAL), label)
        # D1: no carrier at all is AC-9. D3c (fully re-pinned forgery) passes the
        # shell guard by construction and is caught by AC-1/AC-6/AC-7 instead.
        with tempfile.TemporaryDirectory() as td:
            link = Path(td) / "link"
            link.symlink_to(CARRIER, target_is_directory=True)
            result = run_guard(release_env(link))
            self.assertEqual(result.returncode, 1)
            self.assertIn("is not a real directory", result.stderr)  # D10

    # AC-12
    def test_release_requirements_pin_the_carrier(self):
        env = manifest(f"{VERSION}.env")
        requirements = manifest(f"{VERSION}.requirements")
        for key in ("PLEBIAN_OS_VOICE_CARRIER_DIR", "PLEBIAN_OS_VOICE_CARRIER_SHA256",
                    "PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256", "KILIX_LICENSE_REF"):
            self.assertIn(key, requirements)
            self.assertEqual(requirements[key], env[key], key)
        self.assertEqual(env["PLEBIAN_OS_VOICE_CARRIER_DIR"],
                         f"releases/{VERSION}-model-compliance")
        self.assertEqual(env["PLEBIAN_OS_VOICE_CARRIER_SHA256"],
                         sha256((CARRIER / "CARRIER.json").read_bytes()))
        self.assertEqual(env["PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256"],
                         sha256((CARRIER / "ACCEPTANCE.json").read_bytes()))


if __name__ == "__main__":
    unittest.main()
