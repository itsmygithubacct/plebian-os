import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProvisionPlumbingTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        scripts = [
            "bootstrap.sh",
            *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "build").glob("*.sh"))],
            *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "provision").glob("*.sh"))],
        ]
        subprocess.run(["bash", "-n", *scripts], cwd=ROOT, check=True)

    def test_provision_and_update_pass_generic_desktop_knobs(self):
        required = [
            "KILIX_REF",
            "KILIX_DESKTOP_PROVIDER",
            "KILIX_DESKTOP_COMMAND",
            "KILIX_DESKTOP_NAME",
            "KILIX95_REF",
        ]
        for path in [
            ROOT / "provision" / "plebian-os-provision.sh",
            ROOT / "provision" / "plebian-os-update.sh",
        ]:
            text = path.read_text()
            with self.subTest(path=path.name):
                for key in required:
                    self.assertIn(key, text)

    def test_session_env_writer_uses_shell_escaped_defaults(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("write_session_default", text)
        self.assertIn("printf 'if [ -z", text)
        self.assertNotIn(': "\\${KILIX_DIR:=', text)


if __name__ == "__main__":
    unittest.main()
