#!/usr/bin/env python3
"""Exercise the r2 guard and stable policy together without any real device I/O."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from stable_payload import stable_payload

SHELL = os.environ.get('SR7420_TEST_SHELL', 'sh')
RUNTIME = REPO / 'installer/policy/usr/sbin/sr7420-usb-policy'
STOCK = REPO / 'files/usr/sbin'
BOOT_ID = 'fixture-first-boot'
RELEASE = 'sr7420-usb44'
SERIAL = 'SYNTHETIC-USB'
ROOT_MOUNT = '/dev/sda2 / ext4 rw,relatime 0 0\n'
FIRST_RECEIPT = f'READY externally confirmed after 1 seconds boot={BOOT_ID}\n'
REBOOT_EXIT = 73

SHIM = r'''
mount() { [ ! -e ./fail-mount ]; }
umount() { [ ! -e ./fail-unmount ]; }
sync() { :; }
sleep() { :; }
reboot() { [ "$*" = '-f' ] || exit 74; printf '%s\n' attempted >./reboot; exit 73; }
ubus() { [ "$*" = '-t 2 call network.interface.lan status' ] && [ ! -e ./fail-ubus ] && printf '{}\n'; }
jsonfilter() {
 cat >/dev/null
 [ "$1" = -e ] || return 1
 case "$2" in
 '@.up') [ -e ./fail-lan ] && printf 'false\n' || printf 'true\n';;
 '@["ipv4-address"][0].address') printf '192.0.2.1\n';;
 *) return 1;;
 esac
}
pidof() { [ ! -e "./fail-$1" ]; }
'''


class USBStable(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='sr7420-stable-test-')
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.boot = self.work / 'boot'
        self.boot.mkdir()
        self.root = self.work / 'root'
        for directory in ['boot-state', 'etc/init.d', 'proc/sys/kernel/random',
                          'tmp', 'usr/sbin', 'var/run/ubus', 'sys/class/net/br-lan/brif']:
            (self.root / directory).mkdir(parents=True)
        fixtures = {
            'boot-state/stages.log': '',
            'etc/sr7420-usb-release': RELEASE + '\n',
            'etc/sr7420-usb-serial': SERIAL + '\n',
            'etc/sr7420-usb-disk': 'sda\n',
            'etc/sr7420-device.sha256': 'fixture device files manifest\n',
            'proc/mounts': ROOT_MOUNT,
            'proc/sys/kernel/random/boot_id': BOOT_ID + '\n',
            'var/run/ubus/ubus.sock': '',
            **{f'sys/class/net/br-lan/brif/lan{i}': '' for i in range(1, 4)},
        }
        for name, value in fixtures.items():
            self.write('root/' + name, value)
        for name, value in {
            'release-id': RELEASE, 'usb-serial': SERIAL,
            'bundle-sha256': 'a' * 64, 'boot.sha256': 'fixture boot manifest',
            'root.sha256': 'fixture root manifest', 'device.sha256': 'fixture device DTB manifest',
            'boot-pending': RELEASE,
        }.items():
            self.write('boot/' + name, value + '\n')
        for name, (data, _) in stable_payload(REPO).items():
            target = 'etc/sr7420-policy.sha256' if name == 'policy.sha256' else name
            (self.root / target).write_bytes(data)

        common = {
            '/etc/sr7420-usb-release': './root/etc/sr7420-usb-release',
            '/etc/sr7420-usb-disk': './root/etc/sr7420-usb-disk',
            '/etc/sr7420-usb-serial': './root/etc/sr7420-usb-serial',
            '/proc/mounts': './root/proc/mounts',
            '/proc/sys/kernel/random/boot_id': './root/proc/sys/kernel/random/boot_id',
            '/tmp/sr7420-usb-management-confirmed': './root/tmp/sr7420-usb-management-confirmed',
            '/boot-state/stages.log': './root/boot-state/stages.log',
        }
        self.script('policy', RUNTIME, common | {
            '/tmp/sr7420-usb-policy.': './root/tmp/sr7420-usb-policy.',
            'BOOT=$MOUNT_DIR': 'BOOT=./boot',
            'verify_policy_files /': 'verify_policy_files ./root',
            ' / sha256sum ': ' ./root sha256sum ',
            '/usr/sbin/sr7420-usb-confirm --check': 'sh ./confirm --check',
            'limit=125': 'limit=3', 'limit=110': 'limit=3',
        })
        self.script('confirm', STOCK / 'sr7420-usb-confirm', common | {
            '-S /var/run/ubus/ubus.sock': '-f ./root/var/run/ubus/ubus.sock',
            '/sys/class/net/br-lan/brif/': './root/sys/class/net/br-lan/brif/',
        })
        self.script('guard', STOCK / 'sr7420-boot-guard', common | {
            '/usr/sbin/sr7420-usb-confirm --check': 'sh ./confirm --check',
            '/boot/boot-': './boot/boot-', ' /boot': ' ./boot',
            '/proc/sysrq-trigger': './sysrq-trigger', '-lt 120': '-lt 3',
        })
        self.identity = self.command('policy', 'fingerprint', './boot', './root',
                                     'sha256sum', './identity').strip()
        self.assertRegex(self.identity, r'^[0-9a-f]{64}$')

    def script(self, name, source, replacements):
        lines = source.read_text(encoding='utf-8').splitlines(keepends=True)
        text = ''.join(lines[1:])
        for original, replacement in replacements.items():
            text = text.replace(original, replacement)
        self.write(name, lines[0] + SHIM + text)

    def write(self, name, value):
        (self.work / name).write_bytes(value.encode())

    def command(self, script, *args, rc=0, external=False):
        env = os.environ.copy()
        env.pop('SSH_CONNECTION', None)
        if external:
            env['SSH_CONNECTION'] = '192.0.2.2 34567 192.0.2.1 22'
        result = subprocess.run([SHELL, './' + script, *args], cwd=self.work,
                                env=env, capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, rc, (script, args, result.stdout, result.stderr))
        return result.stdout

    @property
    def marker(self):
        return self.root / 'tmp/sr7420-usb-management-confirmed'

    def request(self, confirmed=False):
        self.write('boot/stable-request', self.identity + '\n')
        if confirmed:
            self.write('boot/stable-confirmed', self.identity + '\n')

    def test_first_confirmation_is_accepted_by_original_guard(self):
        self.assertIn('stable=disabled', self.command('policy', 'status'))
        self.command('policy', 'watch')
        self.assertFalse(self.marker.exists())
        self.request()
        self.assertIn('stable=pending-first-external-confirmation', self.command('policy', 'status'))
        self.command('confirm', rc=1)
        self.command('policy', 'watch', rc=1)
        self.assertFalse(self.marker.exists())
        self.command('confirm', external=True)
        self.command('policy', 'watch', rc=1)
        self.assertFalse((self.boot / 'stable-confirmed').exists())
        self.command('guard')
        self.assertFalse((self.boot / 'boot-pending').exists())
        self.assertEqual((self.boot / 'boot-ready').read_text().strip(), BOOT_ID)
        self.command('policy', 'watch')
        self.assertIn('stable=confirmed', self.command('policy', 'status'))
        # A fresh boot does not inherit the previous boot's temporary marker.
        self.marker.unlink()
        self.write('boot/boot-pending', RELEASE + '\n')
        self.write('root/proc/sys/kernel/random/boot_id', 'fixture-later-boot\n')
        self.command('policy', 'watch')
        self.assertEqual(self.marker.read_text().strip(), 'fixture-later-boot')
        self.command('guard')
        self.assertFalse((self.boot / 'boot-pending').exists())
        self.assertFalse((self.work / 'reboot').exists())

    def test_stale_or_incomplete_receipts_do_not_arm_stable(self):
        self.request()
        self.command('confirm', external=True)
        external = (self.root / 'boot-state/stages.log').read_text()
        self.write('root/boot-state/stages.log', external + FIRST_RECEIPT)
        self.write('boot/boot-ready', 'fixture-older-boot\n')
        self.command('policy', 'watch', rc=1)
        self.write('boot/boot-ready', BOOT_ID + '\n')
        self.command('policy', 'watch', rc=1)
        (self.boot / 'boot-pending').unlink()
        self.write('root/boot-state/stages.log', external + FIRST_RECEIPT.replace(BOOT_ID, 'fixture-older-boot'))
        self.command('policy', 'watch', rc=1)
        self.assertFalse((self.boot / 'stable-confirmed').exists())

    def test_guard_ready_without_current_external_confirmation_does_not_arm(self):
        self.request()
        self.command('confirm', external=True)
        self.command('guard')
        self.write('root/boot-state/stages.log', FIRST_RECEIPT)
        self.command('policy', 'watch', rc=1)
        self.assertFalse((self.boot / 'stable-confirmed').exists())

    def test_unhealthy_stable_boot_still_rolls_back(self):
        self.request(confirmed=True)
        (self.work / 'fail-dropbear').touch()
        self.command('policy', 'watch', rc=1)
        self.assertFalse(self.marker.exists())
        self.command('guard', rc=REBOOT_EXIT)
        self.assertTrue((self.work / 'reboot').exists())
        self.assertTrue((self.boot / 'boot-pending').exists())
        self.assertFalse((self.boot / 'boot-ready').exists())

    def test_guard_rechecks_readiness_after_policy_marks_boot(self):
        self.request(confirmed=True)
        self.command('policy', 'watch')
        self.assertTrue(self.marker.exists())
        (self.work / 'fail-lan').touch()
        self.command('guard', rc=REBOOT_EXIT)
        self.assertTrue((self.boot / 'boot-pending').exists())

    def test_changes_or_missing_pending_boot_fail_closed(self):
        self.request(confirmed=True)
        for relative in ['boot/boot.sha256', 'boot/root.sha256', 'boot/bundle-sha256',
                         'boot/device.sha256', 'boot/release-id', 'boot/usb-serial',
                         'root/etc/sr7420-device.sha256', 'root/etc/sr7420-policy.sha256',
                         'root/usr/sbin/sr7420-usb-policy', 'root/proc/mounts']:
            with self.subTest(relative=relative):
                path = self.work / relative
                original = path.read_bytes()
                path.write_bytes(b'changed\n')
                self.command('policy', 'watch', rc=1)
                self.assertFalse(self.marker.exists())
                path.write_bytes(original)
        (self.boot / 'boot-pending').unlink()
        self.command('policy', 'watch')
        self.assertFalse(self.marker.exists())

    def test_mount_failure_and_disable_keep_manual_confirmation(self):
        self.request(confirmed=True)
        for name in ['fail-mount', 'fail-unmount']:
            failure = self.work / name
            failure.touch()
            self.command('policy', 'watch', rc=1)
            self.assertFalse(self.marker.exists())
            failure.unlink()
        self.command('policy', 'disable')
        self.assertFalse((self.boot / 'stable-request').exists())
        self.assertFalse((self.boot / 'stable-confirmed').exists())
        self.command('policy', 'watch')
        self.assertFalse(self.marker.exists())
        self.assertTrue((self.boot / 'boot-pending').exists())


if __name__ == '__main__':
    unittest.main()
