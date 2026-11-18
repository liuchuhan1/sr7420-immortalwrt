#!/usr/bin/env python3
"""Exercise the stock-shell install path with a synthetic, already installed USB."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from stable_payload import autostart_payload, stable_payload

SHELL = os.environ.get('SR7420_TEST_SHELL', 'sh')
BUNDLE = 'a' * 64
SERIAL = 'SYNTHETIC-USB'
SERVICE_LINK = 'root/etc/rc.d/S12sr7420-usb-policy'

SHIM = r'''
id() { [ "$*" = '-u' ] && printf '0\n'; }
uname() { [ "$*" = '-r' ] && cat ./stock-kernel; }
readlink() {
 if [ "$*" = '-f ./sys/class/block/sda/device' ]; then
  printf '%s\n' ./sys/devices/usb1/fixture
 else command readlink "$@"; fi
}
unexpected() { printf '%s\n' "$*" >>./unexpected; exit 78; }
curl() { unexpected curl; }
tar() { unexpected tar; }
mknod() { unexpected mknod; }
busybox() {
 [ "$*" = --list ] || unexpected "busybox $*"
 if [ -f ./no-setsid ]; then printf '%s\n' sh; else printf '%s\n' setsid; fi
}
sync() { :; }
sleep() {
 [ "$*" = 2 ] || unexpected "sleep $*"
 printf '%s\n' "$1" >>./enumeration-waits
 if [ -f ./delayed-partition ]; then
  mv ./delayed-partition ./sys/class/block/sda2/dev
 fi
 if [ -f ./disable-during-wait ]; then rm -f ./autostart-enabled; fi
}
mount() {
 case "$*" in
 '-t tmpfs -o size=196608k,mode=700 tmpfs ./var/sr7420-usb-work.'[0-9]*) :;;
 '-t ext4 -o ro,noload /dev/sda1 ./boot'|'-t ext4 -o ro,noload /dev/sda2 ./root'|\
 '-t ext4 -o rw /dev/sda1 ./boot'|'-t ext4 -o rw /dev/sda2 ./root') :;;
 *) unexpected "mount $*";;
 esac
 printf '%s\n' "$*" >>./mount-calls
}
umount() {
 case "$*" in
 ./boot|./root) :;;
 ./var/sr7420-usb-work.[0-9]*) rm -f "$1/policy-identity";;
 *) unexpected "umount $*";;
 esac
}
'''
WINDOWS_MODE_SHIM = r'''
# Windows fixtures cannot model ext4 modes. Keep real file creation and symlinks.
mkdir() {
 if [ "$1" = -m ]; then [ "$2" = 700 ] || unexpected "mkdir $*"; shift 2; fi
 command mkdir "$@"
}
chmod() { case "$1" in 644|755) :;; *) unexpected "chmod $*";; esac; }
'''


class USBStableInstall(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='sr7420-stable-install-')
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.env = os.environ.copy()
        if os.name == 'nt':
            # MSYS can store Unix symlinks without Windows symlink privileges.
            self.env['MSYS'] = 'winsymlinks:sys'
        data = {
            'stock-kernel': '5.4.196\n', 'proc/device-tree/model': 'ZTE 133\0',
            'proc/meminfo': 'MemAvailable: 500000 kB\n', 'proc/self/mountinfo': '',
            'proc/swaps': '', 'sys/kernel/kexec_loaded': '0\n',
            'autostart-enabled': 'sr7420-usb44\n',
            'sys/class/block/sda/device/vendor': 'SYNTHETIC\n',
            'sys/class/block/sda/device/model': 'USB\n',
            'sys/class/block/sda/removable': '1\n', 'sys/class/block/sda/ro': '0\n',
            'sys/class/block/sda/queue/logical_block_size': '512\n',
            'sys/class/block/sda/size': '4194304\n',
            'sys/class/block/sda/dev': '8:0\n', 'sys/class/block/sda1/dev': '8:1\n',
            'sys/class/block/sda2/dev': '8:2\n', 'dev/sda': '', 'dev/sda1': '', 'dev/sda2': '',
            'sys/devices/usb1/fixture/serial': SERIAL + '\n',
            'boot/release-id': 'sr7420-usb44\n', 'boot/usb-serial': SERIAL + '\n',
            'boot/bundle-sha256': BUNDLE + '\n', 'boot/boot-pending': 'sr7420-usb44\n',
            'boot/board.dtb': 'fixture DTB', 'boot/Image': 'fixture kernel',
            'boot/kexec': '#!/bin/sh\nexit 77\n', 'boot/pci-quiesce': '#!/bin/sh\nexit 77\n',
            'root/sbin/init': '#!/bin/sh\nexit 77\n',
            'root/usr/sbin/sr7420-ram-init': '#!/bin/sh\nexit 77\n',
            'root/etc/sr7420-usb-release': 'sr7420-usb44\n',
            'root/etc/sr7420-usb-serial': SERIAL + '\n', 'root/etc/device.bin': 'fixture calibration',
            'root/etc/config/network': 'fixture preserved configuration\n',
        }
        for name, value in data.items():
            self.write(name, value.encode())
        for name in ['boot/kexec', 'boot/pci-quiesce', 'root/sbin/init', 'root/usr/sbin/sr7420-ram-init']:
            (self.work / name).chmod(0o755)
        for name in ['root/etc/init.d', 'root/etc/rc.d', 'tmp', 'var']:
            (self.work / name).mkdir()
        self.manifest('boot', 'boot/boot.sha256', ['Image', 'kexec', 'pci-quiesce'])
        self.manifest('boot', 'boot/device.sha256', ['board.dtb'])
        self.manifest('root', 'boot/root.sha256', ['sbin/init', 'usr/sbin/sr7420-ram-init'])
        self.manifest('root', 'root/etc/sr7420-device.sha256', ['etc/device.bin'])
        for name, (payload, _) in stable_payload(REPO).items():
            self.write('policy/' + name, payload)

        source = (REPO / 'installer/sr7420-usb.sh.in').read_text(encoding='utf-8')
        source = source.replace('mkdir "$WORK/boot" "$WORK/root"', ':')
        source = source.replace('"$n" -lt 75', '"$n" -lt 3')
        for original, fixture in {
            '__BUNDLE_SHA256__': BUNDLE, '__BUNDLE_URL__': 'https://example.invalid/bundle.tar.gz',
            '/sys/class/block': './sys/class/block', '/proc/device-tree/model': './proc/device-tree/model',
            '/proc/self/mountinfo': './proc/self/mountinfo', '/proc/meminfo': './proc/meminfo',
            '/proc/swaps': './proc/swaps', '/tmp/sr7420-usb.lock': './tmp/sr7420-usb.lock',
            '/sys/kernel/kexec_loaded': './sys/kernel/kexec_loaded', '/sbin/reboot': './stock-reboot',
            '/Plugin/sr7420-usb-autostart/enabled': './autostart-enabled',
            '/var/sr7420-usb-work.': './var/sr7420-usb-work.',
            '$WORK/boot': './boot', '$WORK/root': './root',
            '-b "/dev/$name"': '-f "./dev/$name"',
        }.items():
            source = source.replace(original, fixture)
        shebang, body = source.split('\n', 1)
        shim = SHIM + (WINDOWS_MODE_SHIM if os.name == 'nt' else '')
        self.write('sr7420-usb.sh', (shebang + '\nexport PATH=/usr/sbin:/usr/bin:/sbin:/bin\n' + shim + body).encode())

    def write(self, name, data):
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def manifest(self, base, output, names):
        lines = [f'{hashlib.sha256((self.work / base / n).read_bytes()).hexdigest()}  {n}\n' for n in names]
        self.write(output, ''.join(lines).encode())

    def run_installer(self, args=('install', '--stable'), expected=0, input_text=None):
        result = subprocess.run([SHELL, './sr7420-usb.sh', *args], cwd=self.work,
                                env=self.env, input=input_text, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertFalse((self.work / 'unexpected').exists())
        self.assertFalse((self.work / 'tmp/sr7420-usb.lock').exists())
        self.assertEqual(list((self.work / 'var').iterdir()), [])
        return result.stdout + result.stderr

    def test_install_reuses_r2_and_preserves_existing_files(self):
        protected = ['boot/Image', 'boot/root.sha256', 'boot/boot-pending',
                     'root/etc/config/network', 'root/etc/device.bin']
        before = [(self.work / p).read_bytes() for p in protected]
        self.assertIn('no download or format needed', self.run_installer())
        self.assertEqual(before, [(self.work / p).read_bytes() for p in protected])
        request = (self.work / 'boot/stable-request').read_bytes()
        self.assertRegex(request, rb'^[0-9a-f]{64}\n$')
        self.assertFalse((self.work / 'boot/stable-confirmed').exists())
        link = subprocess.check_output([SHELL, '-c', f'test -L ./{SERVICE_LINK} && readlink ./{SERVICE_LINK}'],
                                       cwd=self.work, env=self.env, text=True, timeout=10)
        self.assertEqual(link.strip(), '../init.d/sr7420-usb-policy')
        for name, (data, _) in stable_payload(REPO).items():
            target = 'etc/sr7420-policy.sha256' if name == 'policy.sha256' else name
            self.assertEqual((self.work / 'root' / target).read_bytes(), data)
        self.assertIn('previous USB boot was not confirmed ready', self.run_installer(('boot',), expected=1))

    def test_repeat_preserves_only_confirmation_bound_to_current_identity(self):
        self.run_installer()
        identity = (self.work / 'boot/stable-request').read_bytes()
        self.write('boot/stable-confirmed', identity)
        self.run_installer()
        self.assertEqual((self.work / 'boot/stable-confirmed').read_bytes(), identity)
        self.write('boot/stable-request', b'previous-policy\n')
        self.run_installer()
        self.assertEqual((self.work / 'boot/stable-request').read_bytes(), identity)
        self.assertFalse((self.work / 'boot/stable-confirmed').exists())

    def test_missing_or_invalid_installation_does_not_erase(self):
        self.write('boot/root.sha256', b'bad manifest\n')
        self.assertIn('requires --erase', self.run_installer(expected=1))
        self.assertNotIn('-o rw', (self.work / 'mount-calls').read_text())
        self.assertFalse((self.work / 'boot/stable-request').exists())

    def test_bad_payload_and_mounted_usb_stop_before_writable_media(self):
        self.write('proc/self/mountinfo', b'30 1 8:2 / /media/usb rw - ext4 /dev/sda2 rw\n')
        self.assertIn('mounted; refusing operation', self.run_installer(expected=1))
        self.assertFalse((self.work / 'mount-calls').exists())
        self.write('proc/self/mountinfo', b'')
        self.write('policy/usr/sbin/sr7420-usb-policy', b'bad payload\n')
        self.assertIn('invalid stable policy payload', self.run_installer(expected=1))
        self.assertNotIn('ext4', (self.work / 'mount-calls').read_text())

    def test_unmanaged_service_is_not_overwritten(self):
        self.write(SERVICE_LINK, b'not a managed symlink\n')
        self.assertIn('unmanaged policy service entry', self.run_installer(expected=1))
        self.assertEqual((self.work / SERVICE_LINK).read_bytes(), b'not a managed symlink\n')
        self.assertFalse((self.work / 'root/usr/sbin/sr7420-usb-policy').exists())
        self.assertFalse((self.work / 'boot/stable-request').exists())

    def test_wrong_modes_stop_without_mounting(self):
        self.assertIn('requires install', self.run_installer(('boot', '--stable'), expected=1))
        for option in ('--erase', '--boot', '--retry', '--load-only'):
            args = ('install', '--stable', '--autostart', option)
            self.assertIn('--autostart requires install', self.run_installer(args, expected=1))
        self.assertIn('--autostart requires install', self.run_installer(('boot', '--autostart'), expected=1))
        self.write('stock-kernel', b'6.18.60\n')
        self.assertIn('return to the validated stock system', self.run_installer(expected=1))
        self.assertFalse((self.work / 'mount-calls').exists())

    def autostart_fixture(self):
        for name, (payload, _) in autostart_payload(REPO).items():
            self.write('autostart/' + name, payload)
        self.write('autostart/manage.sh', b'#!/bin/sh\nprintf "%s\\n" "$@" >./autostart-called\nif [ -f ./capture-login ]; then cat >./autostart-login; fi\n')
        names = ['guest-config.sh', 'guest.sh', 'host.sh', 'manage.sh']
        self.manifest('autostart', 'autostart/autostart.sha256', names)

    def test_autostart_only_verifies_existing_media_then_calls_manager(self):
        self.autostart_fixture()
        self.run_installer(('install', '--autostart'))
        arguments = (self.work / 'autostart-called').read_text().splitlines()
        self.assertEqual(arguments[0::2], ['install', SERIAL])
        manifests = ['boot/boot.sha256', 'boot/device.sha256', 'boot/root.sha256', 'root/etc/sr7420-device.sha256']
        self.assertEqual(arguments[3], ':'.join(hashlib.sha256((self.work / p).read_bytes()).hexdigest() for p in manifests))
        self.assertNotIn('-o rw', (self.work / 'mount-calls').read_text())
        self.assertFalse((self.work / 'boot/stable-request').exists())
        self.assertEqual((self.work / 'boot/boot-pending').read_text(), 'sr7420-usb44\n')

    def test_autostart_accepts_credentials_as_parameters(self):
        self.autostart_fixture()
        self.write('capture-login', b'')
        self.run_installer(('install', '--autostart', '--tnu', 'root', '--tnp', 'stock password'))
        self.assertEqual((self.work / 'autostart-login').read_text(), 'root\nstock password\n')
        self.assertNotIn('stock password', (self.work / 'autostart-called').read_text())

    def test_autostart_retains_stdin_credentials(self):
        self.autostart_fixture()
        self.write('capture-login', b'')
        self.run_installer(('install', '--autostart'), input_text='root\nstock password\n')
        self.assertEqual((self.work / 'autostart-login').read_text(), 'root\nstock password\n')

    def test_credential_parameters_require_a_pair_and_autostart(self):
        self.autostart_fixture()
        for args, message in [
            (('install', '--autostart', '--tnu', 'root'), '--tnu and --tnp must be supplied together'),
            (('install', '--autostart', '--tnp', 'secret'), '--tnu and --tnp must be supplied together'),
            (('install', '--tnu', 'root', '--tnp', 'secret'), '--tnu/--tnp require install --autostart'),
        ]:
            self.assertIn(message, self.run_installer(args, expected=1))
            self.assertFalse((self.work / 'autostart-called').exists())

    def test_autostart_and_stable_share_one_verified_usb(self):
        self.autostart_fixture()
        self.assertIn('stable requested', self.run_installer(('install', '--stable', '--autostart')))
        self.assertTrue((self.work / 'autostart-called').exists())
        self.assertTrue((self.work / 'boot/stable-request').exists())

    def test_corrupt_autostart_payload_fails_before_usb_mount(self):
        self.autostart_fixture()
        self.write('autostart/guest.sh', b'invalid')
        self.assertIn('invalid autostart payload', self.run_installer(('install', '--autostart'), expected=1))
        self.assertNotIn('ext4', (self.work / 'mount-calls').read_text())
        self.assertFalse((self.work / 'autostart-called').exists())

    def attempt_auto_boot(self):
        return self.run_installer(
            ('boot', '--serial', SERIAL, '--autostart-pin', ':'.join(['0' * 64] * 4)), expected=1)

    def test_changed_usb_manifest_pin_blocks_autostart_before_handover(self):
        (self.work / 'boot/boot-pending').unlink()
        self.assertIn('USB manifests changed', self.attempt_auto_boot())
        self.assertFalse((self.work / 'boot/boot-pending').exists())
        self.assertNotIn('-o rw', (self.work / 'mount-calls').read_text())

    def test_autostart_waits_for_partitions_then_respects_pending(self):
        (self.work / 'sys/class/block/sda2/dev').rename(self.work / 'delayed-partition')
        output = self.attempt_auto_boot()
        self.assertIn('USB ready after 2 seconds', output)
        self.assertIn('previous USB boot was not confirmed ready', output)
        self.assertEqual((self.work / 'enumeration-waits').read_text().splitlines(), ['2'])
        self.assertEqual((self.work / 'boot/boot-pending').read_text(), 'sr7420-usb44\n')
        self.assertNotIn('-o rw', (self.work / 'mount-calls').read_text())

    def test_missing_usb_times_out_before_mounting(self):
        (self.work / 'sys/class/block/sda').rename(self.work / 'unavailable-disk')
        (self.work / 'boot/boot-pending').unlink()
        self.assertIn('USB enumeration timed out', self.attempt_auto_boot())
        self.assertEqual((self.work / 'enumeration-waits').read_text().splitlines(), ['2'] * 3)
        self.assertFalse((self.work / 'mount-calls').exists())
        self.assertFalse((self.work / 'boot/boot-pending').exists())

    def test_wrong_usb_is_refused_without_waiting(self):
        self.write('sys/devices/usb1/fixture/serial', b'ANOTHER-USB\n')
        self.assertIn('USB serial does not match autostart configuration', self.attempt_auto_boot())
        self.assertFalse((self.work / 'enumeration-waits').exists())
        self.assertFalse((self.work / 'mount-calls').exists())

    def test_disabling_stops_enumeration_without_mounting(self):
        (self.work / 'sys/class/block/sda2/dev').unlink()
        self.write('disable-during-wait', b'')
        self.assertIn('autostart disabled', self.attempt_auto_boot())
        self.assertEqual((self.work / 'enumeration-waits').read_text().splitlines(), ['2'])
        self.assertFalse((self.work / 'mount-calls').exists())

    def test_boot_without_stock_recovery_stops_before_loading_or_pending(self):
        pending = self.work / 'boot/boot-pending'
        pending.unlink()
        self.assertIn('stock reboot command unavailable', self.run_installer(('boot',), expected=1))
        self.write('stock-reboot', b'#!/bin/sh\nexit 77\n')
        (self.work / 'stock-reboot').chmod(0o755)
        self.write('no-setsid', b'')
        self.assertIn('stock recovery cannot detach', self.run_installer(('boot',), expected=1))
        self.assertFalse(pending.exists())
        self.assertNotIn('-o rw', (self.work / 'mount-calls').read_text())


if __name__ == '__main__':
    unittest.main()
