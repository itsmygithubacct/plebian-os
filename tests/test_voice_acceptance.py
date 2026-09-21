import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))
import build_vm_image as vm  # noqa: E402


class VoiceAcceptanceTests(unittest.TestCase):
    def test_read_aloud_policy_requires_the_skipped_dictation_stamp(self):
        command = vm._voice_acceptance_command("0")
        self.assertIn('PLEBIAN_OS_INSTALL_VOICE_MODEL:-0', command)
        for tool in ("kilix-tts", "kilix-stt", "kilix-voiced"):
            self.assertIn(tool, command)
        self.assertIn('--version', command)
        self.assertIn('kilix-tts" --print', command)
        self.assertIn('kilix-stt" --print', command)
        self.assertIn('kilix-stt" --models --json', command)
        self.assertIn("kilix.speech.models/v1", command)
        self.assertIn("libvosk=skipped", command)
        self.assertIn("model-small-en-us=skipped", command)
        self.assertNotIn("lib/current/libvosk.so", command)

    def test_every_policy_requires_the_guest_to_hold_no_model_weights(self):
        """OD-S, as a guest check, under both policies.

        Before OD-BB the dictation policy demanded an installed model and its
        promoted symlink. It now demands their absence, under the promoted name
        and under any immutable `vosk-model-*` generation, so a fetch that
        landed but was never promoted is caught too.
        """
        for policy in ("0", "1"):
            command = vm._voice_acceptance_command(policy)
            with self.subTest(policy=policy):
                self.assertIn('m="$d/voice/models/small-en-us"', command)
                self.assertIn('test ! -e "$m" && test ! -L "$m"', command)
                self.assertIn("-name 'vosk-model-*'", command)
                self.assertIn('test ! -e "$l" && test ! -L "$l"', command)
                self.assertIn("libvosk=skipped", command)
                self.assertIn("model-small-en-us=skipped", command)
                # The recognition smoke needed weights, so it cannot survive
                # their removal: a guest check that loaded a model would pass
                # only on an image that broke the decision.
                self.assertNotIn("VoskStt", command)
                self.assertNotIn("recognizer", command)
                self.assertNotIn("dictation=ready", command)
                self.assertNotIn('$l/libvosk.so', command)
                self.assertNotIn("Extracted member: vosk/libvosk.so", command)
                self.assertNotIn(
                    "Archive directory: vosk-model-small-en-us-0.15", command)
                # Read-aloud still has to work out of the box.
                self.assertIn("EspeakTts", command)
                self.assertIn("kilix voice is working", command)
                self.assertIn('KILIX_DATA_HOME="$d" PYTHONPATH=', command)

    def test_dictation_policy_requires_the_advertised_first_use_pins(self):
        """Policy 1 now means "this release advertises a first-use pull"."""
        command = vm._voice_acceptance_command("1")
        self.assertIn('l="$d/voice/lib/current"', command)
        self.assertIn('kilix-voice-$KILIX_VOICE_REF', command)
        self.assertIn('KILIX_VOICE_LIB_URL', command)
        self.assertIn('KILIX_VOICE_MODEL_URL', command)
        self.assertIn('KILIX_VOICE_MODEL_SHA256', command)
        self.assertIn('kilix-voice=$KILIX_VOICE_REF', command)
        # The stamp records the pins as advertised and the assets as skipped —
        # never as an installed closure.
        self.assertNotIn(
            'libvosk=$KILIX_VOICE_LIB_VERSION+$KILIX_VOICE_LIB_SHA256',
            command,
        )
        self.assertNotIn(
            'model-small-en-us=$KILIX_VOICE_MODEL_SHA256', command
        )
        self.assertIn("/etc/plebian-os/build-info.env", command)
        self.assertIn('kilix-stt" --models --json', command)
        self.assertIn("install_and_default_argv", command)

    def test_unknown_voice_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            vm._voice_acceptance_command("yes")

    def test_model_catalog_validation_is_versioned_and_fail_closed(self):
        script = vm._voice_model_catalog_validation_script()

        def validate(document):
            return subprocess.run(
                [sys.executable, "-c", script],
                input=json.dumps(document),
                text=True,
                capture_output=True,
                check=False,
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = []
            for model, engine, supported, size, human_size in (
                ("small-en-us", "vosk", True, 41205931, "39.3 MiB"),
                ("lgraph-en-us", "vosk", True, 130557655, "124.5 MiB"),
                (
                    "vibevoice-asr-bitnet", "vibevoice", False,
                    1705771590, "1.6 GiB",
                ),
            ):
                records.append({
                    "id": model,
                    "engine": engine,
                    "runtime_supported": supported,
                    "download_bytes": size,
                    "download_size": human_size,
                    "installed": False,
                    "selected": model == "small-en-us",
                    "path": str(root / model),
                    "summary": f"{model} fixture summary",
                    "install_and_default_argv": [
                        "kilix", "stt", "--install", model,
                        "--default", model,
                    ],
                })
            document = {
                "schema": "kilix.speech.models/v1",
                "default_model": "small-en-us",
                "models": records,
            }
            accepted = validate(document)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            def clone():
                return json.loads(json.dumps(document))

            invalid_documents = []
            invalid = clone()
            invalid["schema"] = "kilix.speech.models/v2"
            invalid_documents.append((
                "schema", invalid, "unknown speech-model catalog schema",
            ))
            invalid = clone()
            invalid["models"][0]["download_bytes"] += 1
            invalid_documents.append((
                "exact bytes", invalid, "download size differs",
            ))
            invalid = clone()
            invalid["models"][0]["runtime_supported"] = 1
            invalid_documents.append((
                "boolean runtime support", invalid, "runtime support differs",
            ))
            invalid = clone()
            invalid["models"][0]["selected"] = 1
            invalid_documents.append((
                "boolean selected state", invalid, "selected state is invalid",
            ))
            invalid = clone()
            invalid["models"][0]["installed"] = True
            invalid_documents.append((
                "missing files", invalid, "installed state disagrees",
            ))
            for label, invalid, message in invalid_documents:
                with self.subTest(label=label):
                    refused = validate(invalid)
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertIn(message, refused.stderr)

            small = Path(records[0]["path"])
            (small / "conf").mkdir(parents=True)
            (small / "am").mkdir()
            (small / "conf" / "model.conf").write_text("fixture\n")
            (small / "am" / "final.mdl").write_bytes(b"fixture\n")
            refused = validate(document)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("installed state disagrees", refused.stderr)

            document["models"][0]["installed"] = True
            accepted = validate(document)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_dictation_acceptance_is_one_valid_fail_closed_shell_chain(self):
        command = vm._voice_acceptance_command("1")
        self.assertEqual(command.count("model-small-en-us=skipped"), 2)
        self.assertIn("= 1 && for tool", command)
        self.assertIn("done && timeout", command)
        self.assertIn(
            "/etc/plebian-os/build-info.env && KILIX_DATA_HOME=\"$d\" "
            "PYTHONPATH=",
            command,
        )
        syntax = subprocess.run(
            ["bash", "-n", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
