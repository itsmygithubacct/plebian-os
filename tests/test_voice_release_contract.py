import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# OS-V-VERIFY F1, as data rather than prose. These are the two refs that were
# shown, by command, not to carry what the documented acquisition route needs:
#
#   $ grep -E '^KILIX_REF=' releases/0.2.2.env
#   KILIX_REF=62cb5760f2d8f47bf62a7ccbb25c6bc2cebf98e9
#   $ git -C <kilix> ls-tree 62cb5760 third_party/kilix-content
#   160000 commit c275334f34427307747a2fef5608b2c993e22007  third_party/kilix-content
#   $ git -C <kilix-content> cat-file -e c275334:src/kilix_content/first_use.py
#   fatal: path ... exists on disk, but not in 'c275334'          (rc 128)
#   $ git -C <kilix-content> cat-file -e 7543aa30:src/kilix_content/first_use.py
#   (rc 0)                                                   # positive control
#   $ git -C <kilix-content> show c275334:src/kilix_content/catalog/plebian.json
#       | <select vosk ids>   -> []          (7543aa30 -> two vosk records)
#   $ git -C <kilix-voice> grep -c require_covering_receipt ba15d849  -> 0 hits
KILIX_REF_WITHOUT_FIRST_USE = "62cb5760f2d8f47bf62a7ccbb25c6bc2cebf98e9"
KILIX_CONTENT_WITHOUT_FIRST_USE = "c275334f34427307747a2fef5608b2c993e22007"
KILIX_VOICE_REF_WITHOUT_RECEIPT_GATE = "ba15d849486d19967f0e543f21bdfdfaf93df4fe"

# The words every instructing document has to carry while that is true.
GAP_STATEMENT = "not reachable on a 0.2.2 image"

# OS-V-VERIFY F6. (document, a sentence that really was removed, the sentence
# that replaced it). The first four were removed by the OS-V commit from the
# base at 139de5be; the last four by this one, from OS-V's own text.
REWRITTEN_CLAIMS = (
    (
        "RELEASING.md",
        "require `kilix-stt --print` to report `dictation=ready`",
        "require `kilix-stt --print` to produce a dictation report",
    ),
    (
        "RELEASING.md",
        "Both installed Vosk assets must retain readable upstream provenance "
        "and Apache-2.0 license material",
        "these pins are the advertised identity",
    ),
    (
        "RELEASING.md",
        "Require the device-free acceptance smoke to synthesize a phrase with "
        "real espeak, load the pinned Vosk library/model, and recognize "
        "nonempty text",
        "**Require the guest to hold no speech-model weights**",
    ),
    (
        "RELEASING.md",
        "Verify the installed library/model match the exact release stamp",
        "A model present on a fresh image is a release failure",
    ),
    (
        "RELEASING.md",
        "Then acquire the model the way a user does: run `kilix models "
        "install vosk-model-small-en-us-0.15`",
        "The first-use acceptance leg is deferred and must not be attempted "
        "on a 0.2.2 image",
    ),
    (
        "releases/0.2.2-notes.md",
        "The first time you ask for dictation, Kilix shows the model's "
        "identity",
        "on a 0.2.2 image dictation is neither installed nor acquirable "
        "through the documented route",
    ),
    (
        "UPGRADING.md",
        "The first time dictation is wanted, Kilix shows the model, its "
        "upstream source",
        "it cannot acquire one at all",
    ),
    (
        "CHANGELOG.md",
        "dictation model is acquired the first time it is wanted",
        "dictation model is to be acquired the first time it is wanted",
    ),
)


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
        self.assertIn('for entry in "$models_root"/vosk-model-*', provision)
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
        # OS-V-VERIFY F1. The route these documents name is not in the closure
        # this release pins, so a document may name the command only as part of
        # saying that it cannot be run here. Any document that mentions it must
        # carry the gap statement, in those words, in the same file.
        for name, text in documents.items():
            collapsed = " ".join(text.split())
            with self.subTest(document=name, requirement="the honest gap"):
                self.assertIn(GAP_STATEMENT, collapsed)
                if "kilix models install vosk-model-small-en-us-0.15" in (
                        collapsed):
                    self.assertIn(
                        "0.2.2 image", collapsed,
                        "a document naming the command must say where it does "
                        "not run",
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

        # And the claims that are now false.
        #
        # OS-V-VERIFY F6: the three strings that used to be checked here had
        # never appeared in any of these documents, at any ref, so the block
        # could not catch a document reverted to claim provisioning — it was
        # decorative. Each entry below is a sentence that really was in the
        # file and really was taken out, paired with the sentence that replaced
        # it. Asserting both halves is what gives the assertion bite: a revert
        # of that edit restores the first string and destroys the second, so it
        # fails twice and for the right reason, and a pair whose "removed" half
        # never existed would fail the moment it was written.
        for name, removed, replacement in REWRITTEN_CLAIMS:
            collapsed = " ".join(documents[name].split())
            with self.subTest(document=name, removed=removed[:48]):
                self.assertNotIn(removed, collapsed)
                self.assertIn(
                    replacement, collapsed,
                    "the sentence that replaced it must be here, or this "
                    "assertion is about nothing",
                )
                self.assertNotIn(
                    removed, replacement,
                    "a replacement containing the removed text is not a "
                    "replacement",
                )


    def test_the_pinned_closure_can_acquire_the_model_with_acceptance(self):
        """DELIBERATELY FAILING — OS-V-VERIFY F1 (Critical), and F2 (High).

        This test does not describe a defect in this repository's code. It
        holds open a gap between what 0.2.2's documents describe and what the
        closure 0.2.2 pins can do, so that the gap cannot be closed by
        forgetting about it. It fails today, on purpose, and the message says
        exactly what has to land for it to pass. **Do not weaken it to make the
        suite green**: weakening it would restore the false-delivery shape the
        carrier design calls D6, which is the thing OD-BB exists to prevent.

        plebian-os cannot fix this from inside plebian-os. The acquisition flow
        lives in kilix-content and reaches the image only through Kilix's
        `third_party/kilix-content` submodule, and the receipt gate that stops
        the catalog row's own action from fetching unconsented lives in
        kilix-voice. Both arrive here as ref advances in `releases/0.2.2.env`.
        """
        manifest = _manifest(ROOT / "releases" / "0.2.2.env")
        owed = []
        if manifest.get("KILIX_REF") == KILIX_REF_WITHOUT_FIRST_USE:
            owed.append(
                "1. THE CONTENT CHAIN. releases/0.2.2.env pins\n"
                f"   KILIX_REF={KILIX_REF_WITHOUT_FIRST_USE}, whose\n"
                f"   third_party/kilix-content gitlink is\n"
                f"   {KILIX_CONTENT_WITHOUT_FIRST_USE}. That commit has no\n"
                "   src/kilix_content/first_use.py and no\n"
                "   vosk-model-small-en-us-0.15 asset record, and the image\n"
                "   serves kilix_content from exactly that submodule\n"
                "   (build/build_vm_image.py, $KILIX_DIR/third_party/\n"
                "   kilix-content/src). So on a 0.2.2 image\n"
                "   `kilix models install vosk-model-small-en-us-0.15` cannot\n"
                "   resolve the asset and no licence screen exists to show.\n"
                "   WHAT MUST LAND: kilix-content's first-use flow and the\n"
                "   vosk record are merged and released (they exist today on\n"
                "   the unmerged work/0.2.2-c1-first-use, at 7543aa30); a\n"
                "   Kilix commit advances third_party/kilix-content to a\n"
                "   commit carrying both; and KILIX_REF here advances to that\n"
                "   Kilix commit. Only the last of those three is an edit to\n"
                "   this repository.")
        if (manifest.get("KILIX_VOICE_REF")
                == KILIX_VOICE_REF_WITHOUT_RECEIPT_GATE):
            owed.append(
                "2. THE RECEIPT GATE ON THE ADVERTISED ACTION.\n"
                f"   KILIX_VOICE_REF={KILIX_VOICE_REF_WITHOUT_RECEIPT_GATE}\n"
                "   has no covering-receipt check, so the catalog row action\n"
                "   this repository *requires* every row to carry,\n"
                "   `kilix stt --install M --default M`, still reaches a\n"
                "   39.3 MiB download with no licence shown and no receipt\n"
                "   written. OD-BB's 'the licence is shown and accepted\n"
                "   before any fetch' is false on the surface users reach\n"
                "   while that is the pin. WHAT MUST LAND: KILIX_VOICE_REF\n"
                "   advances to a kilix-voice commit whose install routes\n"
                "   call require_covering_receipt first and exit 3\n"
                "   (LICENCE_REFUSED_EXIT) without one.")
        if owed:
            self.fail(
                "0.2.2 advertises a first-use acquisition route its own\n"
                "pinned closure cannot run. This failure is deliberate and\n"
                "recorded (OS-V-VERIFY F1/F2, OS-V-FIX-IMPL.md); it is the\n"
                "only failure in this suite besides the sanctioned undated\n"
                "0.2.2 CHANGELOG heading. What is owed:\n\n"
                + "\n\n".join(owed)
                + "\n\nWhen both pins have advanced, this test passes with no\n"
                "edit to it, and the cross-repo equality OS-V-VERIFY F7 defers\n"
                "becomes writable at the same moment, because the release\n"
                "then pins a kilix-content ref to test against.")

    def test_no_provisioning_path_runs_the_advertised_install_action(self):
        """The row is required; running it is not this image's business.

        `validate_voice_model_catalog` requires every catalog row to carry
        `kilix stt --install M --default M`, because that is the one shared
        install contract the model-management surfaces publish. Requiring a row
        to *carry* an action and *running* it are different things, and the
        difference now matters: with kilix-voice's weights gate that action
        exits 3 (LICENCE_REFUSED_EXIT) on a machine with no covering receipt,
        which every freshly provisioned 0.2.2 image is. A provisioning or
        verification path that ran it would therefore either fail the image on
        a refusal that is correct, or — before that gate — fetch the weights
        OD-BB removed. Neither may happen: the only kilix-stt invocations on
        these paths are read-only reports.
        """
        contract = '"kilix", "stt", "--install", model, "--default", model'
        # The two files that require the row carry `--install` exactly once,
        # and that once is the comparison itself. Any second occurrence would
        # be something this image does with the action rather than something it
        # requires of the row, so counting is the whole check.
        for name in ("provision/plebian-os-provision.sh",
                     "build/build_vm_image.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertIn(contract, text)
                self.assertEqual(
                    text.count("--install"), 1,
                    f"{name} may require the install action, never run it")
        for name in ("provision/plebian-os-update.sh",
                     "build/remaster-iso.sh"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertNotIn("--install", text)
        # …and every kilix-stt these paths actually run is a read-only report.
        for name in ("provision/plebian-os-provision.sh",
                     "build/build_vm_image.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            invocations = re.findall(r'kilix-stt"? +(--[a-z-]+)', text)
            with self.subTest(script=name, requirement="read-only only"):
                self.assertTrue(invocations)
                for flag in sorted(set(invocations)):
                    self.assertIn(flag, ("--version", "--print", "--models"))

    def test_the_stamp_assertions_are_anchored_to_whole_lines(self):
        """OS-V-VERIFY F4: mutant MU-09 unanchored these and survived.

        A stamp reading `libvosk=skipped` beside an installed
        `model-small-en-us=<sha>` satisfies an unanchored `grep -q skipped`
        twice over. The behavioural kill is
        test_release_voice_verification_refuses_a_planted_firstboot_model's
        `plant_half_skipped_stamp` arm; this pins the shape of the check so the
        weakening is also visible in the diff.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        for anchored in (
            """grep -Fqx -- 'libvosk=skipped' "$stamp\"""",
            """grep -Fqx -- 'model-small-en-us=skipped' "$stamp\"""",
        ):
            with self.subTest(assertion=anchored):
                self.assertIn(anchored, provision)
        self.assertNotIn("""grep -q -- 'skipped'""", provision)
        self.assertNotIn("""grep -q 'skipped'""", provision)
        # The guest acceptance command is anchored the same way.
        builder = (ROOT / "build" / "build_vm_image.py").read_text(
            encoding="utf-8")
        self.assertIn("grep -Fqx 'libvosk=skipped'", builder)
        self.assertIn("grep -Fqx 'model-small-en-us=skipped'", builder)

    def test_the_advertised_digest_check_is_present_in_the_verifier(self):
        """OS-V-VERIFY F5: mutant MU-15 deleted this and survived.

        The behavioural kill is
        test_release_voice_verification_requires_a_well_formed_advertisement;
        this pins the refusal's presence and its wording, because the wording
        is what that behavioural test matches on.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '[[ "$KILIX_VOICE_MODEL_SHA256" =~ ^[0-9a-fA-F]{64}$ ]]',
            provision)
        self.assertIn(
            "the advertised first-use model digest must be a full SHA-256",
            provision)
        self.assertIn(
            '[[ "$KILIX_VOICE_MODEL_URL" == https://* ]]', provision)
        self.assertIn(
            "the advertised first-use model source must be an HTTPS upstream "
            "URL", provision)

    def test_provisioning_censuses_dictation_assets_before_it_installs(self):
        """OS-V-VERIFY F3: the discriminator must be taken, and taken first.

        The refusal can only tell an image-shipped model from one the user
        accepted if the census is recorded *before* the one step that could
        install anything. A census taken after `pleb install` would call a
        fetch pre-existing and pass it.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("record_voice_dictation_census() {", provision)
        self.assertIn(
            "\nrecord_voice_dictation_census\n", provision,
            "the census function must be defined and also called")
        census = provision.index("\nrecord_voice_dictation_census\n")
        install = provision.index('"$PLEB_DIR/bin/pleb" install')
        verify = provision.index("\n    verify_kilix_voice_install\n")
        self.assertLess(census, install, "the census must precede pleb install")
        self.assertLess(install, verify)
        self.assertIn("PROVISION_COMPLETED_MARKER=/var/lib/plebian-os/"
                      "provisioned", provision)
        # Not seeded from the environment: an ambient value must not be able to
        # turn the image's own absence check into a no-op.
        self.assertNotIn("PROVISION_COMPLETED_MARKER=${", provision)
        self.assertIn(
            "provisioning installed speech-model dictation assets during this "
            "run", provision)


if __name__ == "__main__":
    unittest.main()
