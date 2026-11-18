#!/usr/bin/env python3
"""Exercise autostart hook removal without a device or an LXC container."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1] / 'installer/autostart'
SHELL = os.environ.get('SR7420_TEST_SHELL', 'sh')
BASELINE = b'# nativeC fixture\n::sysinit:/etc/rc\n::respawn:/sbin/getty\n'
ENTRY = '::once:/bin/sh /etc/sr7420-usb-autostart/guest.sh boot'
MARKER = b'sr7420-usb-autostart-v1\n'
HOST_SHIM = r'''
id() { [ "$*" = '-u' ] && printf '0\n'; }
uname() { [ "$*" = '-r' ] && printf '5.4.196\n'; }
readlink() { [ "$*" = '-f /apps' ] && printf '/Plugin\n'; }
sync() { printf '%s\n' stock >>./sync-calls; }
lxc_attach() {
 [ "$1:$2:$3:$4:$5" = '-n:nativeC:--:/bin/sh:-c' ] || return 99
 shift 5
 # Some stock builds return 0 even when the guest command does not finish.
 if [ ! -e ./suppress-attach ]; then /bin/sh -c "$@"; fi
 return 0
}
'''


class AutostartUninstall(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='sr7420-autostart-disable-')
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.write('proc/model', b'ZTE 133\0')
        self.write('proc/mounts', b'root / jffs2 ro 0 0\ntmpfs /var tmpfs rw 0 0\nplugin /Plugin jffs2 rw 0 0\n')
        self.write('guest/mountinfo', b'20 1 0:2 / / rw - overlay overlay rw,upperdir=/apps/apps\n')
        self.write('guest/etc/inittab', BASELINE)
        self.table = self.work / 'guest/etc/inittab'
        self.guest = self.work / 'guest/etc/sr7420-usb-autostart'
        self.host = self.work / 'plugin-state'

        guest = self.adapt('guest-config.sh', {
            'table=/etc/inittab': 'table=./guest/etc/inittab',
            'dir=/etc/sr7420-usb-autostart': 'dir=./guest/etc/sr7420-usb-autostart',
            'mktemp /etc/': 'mktemp ./guest/etc/',
            '/proc/self/mountinfo': './guest/mountinfo',
        })
        # The nativeC build has no sync applet. Only stock may sync the overlay.
        guest = self.inject(guest, 'sync() { touch ./unexpected-guest-sync; return 127; }\n')
        self.write('payload/guest-config.sh', guest.encode())
        host = self.adapt('manage.sh', {
            '/proc/device-tree/model': './proc/model', '/proc/mounts': './proc/mounts',
            '/Plugin/sr7420-usb-autostart': './plugin-state',
            '/var/sr7420-usb-autostart.setup': './setup',
            'lxc-attach -n': 'lxc_attach -n',
        })
        self.write('payload/manage.sh', self.inject(host, HOST_SHIM).encode())

    def write(self, name, data):
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def adapt(self, name, replacements):
        text = (PAYLOAD / name).read_text(encoding='utf-8')
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    @staticmethod
    def inject(script, shim):
        shebang, body = script.split('\n', 1)
        return shebang + '\n' + shim + body

    def provision_fixture(self, *, host=True):
        self.write('guest/etc/sr7420-usb-autostart/managed', MARKER)
        self.write('guest/etc/sr7420-usb-autostart/login', b'fixture-user\nfixture-password\n')
        self.write('guest/etc/sr7420-usb-autostart/guest.sh', b'# synthetic payload\n')
        self.table.write_bytes(BASELINE.replace(b'::respawn:', (ENTRY + '\n::respawn:').encode()))
        if host:
            self.write('plugin-state/managed', MARKER)
            self.write('plugin-state/enabled', b'sr7420-usb44\n')

    def disable(self, expected=0):
        result = subprocess.run([SHELL, './payload/manage.sh', 'disable'], cwd=self.work,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertFalse((self.work / 'unexpected-guest-sync').exists())
        self.assertFalse((self.work / 'setup').exists())
        return result.stdout + result.stderr

    def test_disable_restores_table_and_removes_login(self):
        self.provision_fixture()
        self.assertIn('autostart disabled and saved Telnet login removed', self.disable())
        self.assertFalse(self.guest.exists())
        self.assertFalse(self.host.exists())
        self.assertEqual(self.table.read_bytes(), BASELINE)
        self.assertEqual((self.work / 'sync-calls').read_text().splitlines(), ['stock', 'stock'])

    def test_missing_guest_receipt_leaves_disarmed_state_for_cleanup(self):
        self.provision_fixture()
        self.write('suppress-attach', b'')
        self.assertIn('nativeC cleanup still required', self.disable(expected=1))
        self.assertFalse((self.host / 'enabled').exists())
        self.assertTrue((self.host / 'managed').exists())
        self.assertTrue((self.guest / 'login').exists())
        (self.work / 'suppress-attach').unlink()
        self.disable()
        self.assertFalse(self.guest.exists())
        self.assertFalse(self.host.exists())

    def test_disable_cleans_orphaned_guest_state(self):
        self.provision_fixture(host=False)
        self.disable()
        self.assertFalse(self.guest.exists())
        self.assertEqual(self.table.read_bytes(), BASELINE)


if __name__ == '__main__':
    unittest.main()
