"""A video-only PipeWire setup must leave the Pulse socket to PulseAudio."""
import os
from pathlib import Path
import tempfile
import unittest

from test_audio_device_holdoff import provision_call


class AudioOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / 'etc/wireplumber/wireplumber.conf.d/50pleb-video-only.conf'
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text('context.properties = {\n'
                                '    wireplumber.profile = video-only\n}\n')
        units = self.root / 'usr/lib/systemd/user'
        units.mkdir(parents=True)
        (units / 'pulseaudio.service').write_text('[Service]\nExecStart=/usr/bin/pulseaudio\n')
        self.overrides = self.root / 'etc/systemd/user'

    def configure(self, dry=False):
        return provision_call(f'DRY_RUN={int(dry)}; configure_pulseaudio_ownership', self.root)

    def test_conflicting_service_and_socket_masked_without_touching_video(self):
        for _ in range(2):
            result = self.configure()
            self.assertEqual(result.returncode, 0, result.stderr)
        for unit in ('pipewire-pulse.service', 'pipewire-pulse.socket'):
            self.assertEqual(os.readlink(self.overrides / unit), '/dev/null')
        self.assertFalse((self.overrides / 'pipewire.service').exists())
        self.assertFalse((self.overrides / 'wireplumber.service').exists())
        self.assertFalse((self.overrides / 'pulseaudio.service').exists())

    def test_dry_run_does_not_change_units(self):
        result = self.configure(dry=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.overrides.exists())

    def test_custom_unit_is_preserved_and_no_partial_mask_written(self):
        self.overrides.mkdir(parents=True)
        custom = self.overrides / 'pipewire-pulse.socket'
        custom.write_text('custom configuration\n')
        result = self.configure()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(custom.read_text(), 'custom configuration\n')
        self.assertFalse((self.overrides / 'pipewire-pulse.service').exists())

    def test_other_wireplumber_profiles_are_unchanged(self):
        self.profile.write_text('wireplumber.profile = main\n')
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.overrides.exists())

    def test_missing_pulseaudio_refuses_to_disable_only_audio_server(self):
        (self.root / 'usr/lib/systemd/user/pulseaudio.service').unlink()
        result = self.configure()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.overrides.exists())


if __name__ == '__main__':
    unittest.main()
