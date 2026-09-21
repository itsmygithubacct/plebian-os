import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _manifest(path):
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


class VoiceReleaseContractTests(unittest.TestCase):
    def test_unpinned_install_defaults_to_read_aloud_only(self):
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        update = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        self.assertGreaterEqual(
            remaster.count('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}'), 2)
        self.assertNotIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-1}', remaster)
        self.assertIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}', provision)
        self.assertIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}', update)

    def test_release_manifests_use_the_runtime_checksum_names(self):
        for path in sorted((ROOT / "releases").glob("*.env")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(manifest=path.name):
                self.assertNotRegex(
                    text, r"(?m)^KILIX_VOICE_(?:LIB|MODEL)_SHA=")

    def test_dictation_policy_requires_a_complete_explicit_closure(self):
        for path in sorted((ROOT / "releases").glob("*.env")):
            values = _manifest(path)
            if values.get("PLEBIAN_OS_INSTALL_VOICE_MODEL") != "1":
                continue
            with self.subTest(manifest=path.name):
                self.assertRegex(
                    values.get("KILIX_VOICE_REF", ""), r"^[0-9a-f]{40}$"
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_VERSION", ""),
                    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_URL", ""), r"^https://"
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_SHA256", ""),
                    r"^[0-9a-f]{64}$",
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_MODEL_URL", ""), r"^https://")
                self.assertRegex(
                    values.get("KILIX_VOICE_MODEL_SHA256", ""),
                    r"^[0-9a-f]{64}$",
                )

    def test_0_1_7_pins_the_published_offline_dictation_closure(self):
        values = _manifest(ROOT / "releases" / "0.1.7.env")
        self.assertEqual(values["PLEBIAN_OS_INSTALL_VOICE_MODEL"], "1")
        self.assertEqual(
            values["KILIX_VOICE_REF"],
            "f05b64a7b2bc25fa9a7e2c3ae1e0b848f04a23f6",
        )
        self.assertEqual(values["KILIX_VOICE_LIB_VERSION"], "0.3.45")
        self.assertEqual(
            values["KILIX_VOICE_LIB_URL"],
            "https://files.pythonhosted.org/packages/fc/ca/83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9ff/vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl",
        )
        self.assertEqual(
            values["KILIX_VOICE_LIB_SHA256"],
            "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f",
        )
        self.assertEqual(
            values["KILIX_VOICE_MODEL_URL"],
            "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        )
        self.assertEqual(
            values["KILIX_VOICE_MODEL_SHA256"],
            "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498",
        )

    def test_firstboot_smoke_is_read_aloud_only_and_loads_no_model(self):
        """Read-aloud still works out of the box; recognition is not smoked.

        Recognition cannot be smoke-tested at firstboot any more, because under
        OD-BB the image holds no acoustic model. Keeping the Vosk half would
        mean either an honest image that fails its own acceptance, or a green
        image that still downloads weights unattended. So the smoke proves what
        is really provisioned, and is asserted never to reach for a model.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("run_voice_read_aloud_smoke", provision)
        self.assertNotIn("run_voice_functional_smoke", provision)
        self.assertIn('EspeakTts(voice="en-us", rate=135)', provision)
        self.assertIn("kilix voice is working", provision)
        self.assertIn("espeak produced no PCM", provision)
        for forbidden in (
            "from voicelib.stt import VoskStt",
            "recognizer.start_utterance()",
            "recognizer.end_utterance().strip()",
            "lib_path=library_path",
            "model_path=model_path",
            'voice/models/small-en-us"',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, provision)

    def test_no_provisioning_path_asks_for_model_weights(self):
        """The image's only lever on the weights is the `pleb` handoff.

        `pleb install` reads PLEB_INSTALL_VOICE_MODEL: 1 downloads and installs
        the whole dictation closure, 0 takes the read-aloud-only leg. Both
        provisioning entrypoints must hand over a literal 0. Forwarding the
        release flag — which is what they used to do — is exactly the
        unattended firstboot download OD-BB removed.
        """
        for name in (
            "provision/plebian-os-provision.sh",
            "provision/plebian-os-update.sh",
        ):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertEqual(
                    text.count("PLEB_INSTALL_VOICE_MODEL="), 1, name)
                self.assertNotIn(
                    "PLEB_INSTALL_VOICE_MODEL=$INSTALL_VOICE_MODEL", text)
                self.assertNotIn(
                    "PLEB_INSTALL_VOICE_MODEL=$PLEBIAN_OS_INSTALL_VOICE_MODEL",
                    text,
                )
                self.assertNotIn("PLEB_INSTALL_VOICE_MODEL=1", text)
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("readonly PROVISION_VOICE_WEIGHTS=0", provision)
        self.assertIn(
            '"PLEB_INSTALL_VOICE_MODEL=$PROVISION_VOICE_WEIGHTS"', provision)
        self.assertIn('"PLEB_INSTALL_VOICE_MODEL=0"', (
            ROOT / "provision" / "plebian-os-update.sh"
        ).read_text(encoding="utf-8"))

    def test_no_model_weight_path_is_written_during_provisioning(self):
        """Provisioning verification asserts the weights are absent.

        The old verifier required the promoted `small-en-us` symlink, its
        immutable generation, `libvosk.so` and their provenance files. Every
        one of those is now a refusal instead.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "provisioning left speech-model weights on the image", provision)
        self.assertIn('for generation in "$models_root"/vosk-model-*',
                      provision)
        self.assertIn(
            "provisioning installed the Vosk dictation library", provision)
        self.assertIn(
            "provisioning did not record the skipped Vosk model", provision)
        for forbidden in (
            "verified Vosk small-en-us model is missing",
            "Vosk model small-en-us path is not a generation symlink",
            "Vosk library current path is not a generation symlink",
            "verified Vosk library is missing",
            "kilix-stt did not report dictation=ready",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, provision)

    def test_documents_describe_the_first_use_route_the_code_takes(self):
        """The documents must describe acquisition, not provisioning.

        A document that still says the image installs the model would be the
        false-delivery failure the carrier design calls D6, so each document is
        checked for the route it must describe and against the claim it must no
        longer make. The advertised identity is compared against
        `releases/0.2.2.env` rather than retyped, so the two cannot drift.
        """
        manifest = _manifest(ROOT / "releases" / "0.2.2.env")
        self.assertEqual(manifest["PLEBIAN_OS_INSTALL_VOICE_MODEL"], "1")
        documents = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "CHANGELOG.md",
                "UPGRADING.md",
                "releases/0.2.2-notes.md",
                "RELEASING.md",
                "build/build_vm_image.md",
            )
        }
        for name, text in documents.items():
            with self.subTest(document=name, requirement="first-use route"):
                self.assertIn("first-use", text)
                self.assertIn("advertis", text)
        for name in ("CHANGELOG.md", "UPGRADING.md", "releases/0.2.2-notes.md",
                     "RELEASING.md"):
            with self.subTest(document=name, requirement="the command"):
                self.assertIn(
                    "kilix models install vosk-model-small-en-us-0.15",
                    " ".join(documents[name].split()),
                )
        for name in ("CHANGELOG.md", "releases/0.2.2-notes.md"):
            with self.subTest(document=name, requirement="acceptance first"):
                collapsed = " ".join(documents[name].split())
                self.assertIn("licence", collapsed)
                self.assertIn("licensor", collapsed)
                self.assertIn("before", collapsed)
                self.assertIn("no unattended model download", collapsed)

        # The notes carry the advertised identity; the manifest is the source.
        notes = documents["releases/0.2.2-notes.md"]
        for key in ("KILIX_VOICE_MODEL_URL", "KILIX_VOICE_MODEL_SHA256"):
            with self.subTest(pin=key):
                self.assertIn(manifest[key], notes)
        self.assertIn("vosk-model-small-en-us-0.15", notes)
        self.assertIn(
            "vosk-model-small-en-us-0.15.zip", manifest["KILIX_VOICE_MODEL_URL"])

        # And the claim that is now false.
        for name, text in documents.items():
            collapsed = " ".join(text.split())
            for forbidden in (
                "require the model installed and verified at firstboot",
                "firstboot installs the acoustic model",
                "the image provisions the dictation model",
            ):
                with self.subTest(document=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, collapsed)


if __name__ == "__main__":
    unittest.main()
