#!/usr/bin/env python3
"""Exercise USB preinit hook ordering and reject roots that could reach OEM flash."""
from pathlib import Path
import os, subprocess, tempfile
repo = Path(__file__).resolve().parents[1]
source = (repo / 'files/lib/preinit/81_sr7420_usb_root').read_text()
with tempfile.TemporaryDirectory(prefix='sr7420-preinit-') as temp:
    base = Path(temp)
    for relative in ['etc', 'boot-state', 'proc', 'dev']:
        (base / relative).mkdir()
    (base / 'etc/sr7420-usb-disk').write_text('sda\n')
    (base / 'etc/sr7420-usb-release').write_text('sr7420-usb44\n')
    for name in ['etc/sr7420-usb-disk', 'etc/sr7420-usb-release', 'proc/mounts',
                 'boot-state/stages.log', 'dev/kmsg']:
        source = source.replace('/' + name, str(base / name))
    hooks = (repo / 'tests/fixtures/openwrt-preinit.sh').read_text() + """
preinit_main_hook='before do_mount_root after'
sync() { :; }
reboot() { exit 77; }
"""
    for flag, mounts, expected in [
        ('0', '/dev/sda2 / ext4 rw,relatime 0 0', 'before do_mount_root after'),
        ('1', '/dev/sda2 / ext4 rw,relatime 0 0', 'before after'),
        ('1', '/dev/sda2 / ext4 ro,relatime 0 0', None),
        ('1', '/dev/ram0 / tmpfs rw 0 0', None),
        ('1', '/dev/sdb2 / ext4 rw 0 0', None),
    ]:
        (base / 'proc/mounts').write_text(mounts + '\n')
        env = os.environ.copy(); env['SR7420_USB_ROOT'] = flag
        result = subprocess.run(['bash', '-c', hooks + '\n' + source +
                                 '\nprintf "%s\\n" "$preinit_main_hook"'],
                                env=env, text=True, capture_output=True, timeout=5)
        assert result.returncode == (0 if expected is not None else 77), result
        if expected is not None:
            assert result.stdout.strip() == expected, result
print('Ordinary preinit preserved; only verified writable USB ext4 skips OEM flash-root probing')
