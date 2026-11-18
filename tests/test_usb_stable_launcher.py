#!/usr/bin/env python3
"""Check the optional launcher against the immutable r2 release archive."""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from extend_r2_launcher import BASE_SHA, BUNDLE_SHA, BUNDLE_URL, build
from stable_payload import AUTOSTART_FILES, POLICY_FILES
from verify_usb_bundle import contents, manifest

ORIGINAL = Path(os.environ.get('SR7420_R2_LAUNCHER',
    REPO.parent / 'artifacts-r2/sr7420-usb44-launcher.tar.gz'))
EXECUTABLES = ('sr7420-usb.sh', 'sha256', *('policy/' + name for name in POLICY_FILES),
               *('autostart/' + name for name in AUTOSTART_FILES))


@unittest.skipUnless(ORIGINAL.is_file(), 'Set SR7420_R2_LAUNCHER to the published r2 launcher')
class StableLauncher(unittest.TestCase):
    def test_only_opt_in_payloads_and_wrapper_change(self):
        with tempfile.TemporaryDirectory(prefix='sr7420-stable-archive-') as temp:
            output = Path(temp) / 'launcher.tar.gz'
            report = build(ORIGINAL, output)
            original = ORIGINAL.read_bytes()
            candidate = output.read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest(), BASE_SHA)
            self.assertEqual(hashlib.sha256(candidate).hexdigest(), report['launcher_sha256'])
            self.assertEqual(report['system_bundle_sha256'], BUNDLE_SHA)
            self.assertFalse(report['system_bundle_repacked'])
            self.assertEqual(report['stock_autostart_backend'], 'nativeC-loopback-telnet')

            base = contents(original)
            new = contents(candidate, executables=EXECUTABLES)
            added = {'policy/policy.sha256', *('policy/' + name for name in POLICY_FILES),
                     'autostart/autostart.sha256', *('autostart/' + name for name in AUTOSTART_FILES)}
            self.assertEqual(new.keys() - base.keys(), added)
            self.assertEqual(base.keys() - new.keys(), set())
            for name in base.keys() - {'sr7420-usb.sh', 'launcher.sha256'}:
                self.assertEqual(new[name], base[name], name)
            installer = new['sr7420-usb.sh'].decode()
            self.assertIn('DEFAULT_SHA=' + BUNDLE_SHA, installer)
            self.assertIn('DEFAULT_URL=' + BUNDLE_URL, installer)
            self.assertIn('--stable)', installer)
            self.assertIn('--autostart)', installer)
            self.assertEqual(manifest(new, new['launcher.sha256']), len(new) - 1)
            names = [line.split('  ', 1)[1] for line in new['launcher.sha256'].decode().splitlines()]
            self.assertEqual(set(names), new.keys() - {'launcher.sha256'})
            self.assertEqual(manifest(new, new['policy/policy.sha256'], 'policy/'), len(POLICY_FILES))
            self.assertEqual(manifest(new, new['autostart/autostart.sha256'], 'autostart/'), len(AUTOSTART_FILES))

            repeat = Path(temp) / 'repeat.tar.gz'
            build(ORIGINAL, repeat)
            self.assertEqual(repeat.read_bytes(), candidate)
            with self.assertRaises(FileExistsError):
                build(ORIGINAL, output)
            self.assertEqual(output.read_bytes(), candidate)

    def test_changed_base_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix='sr7420-stable-bad-base-') as temp:
            modified = Path(temp) / 'changed.tar.gz'
            modified.write_bytes(ORIGINAL.read_bytes() + b'changed')
            output = Path(temp) / 'launcher.tar.gz'
            with self.assertRaisesRegex(ValueError, 'exact published r2 launcher'):
                build(modified, output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
