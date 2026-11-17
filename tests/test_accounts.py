#!/usr/bin/env python3
"""Check clean public defaults while accepting locked package service users."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_usb_bundle import verify_accounts

def rejects(callback):
    try: callback()
    except AssertionError: return
    raise AssertionError('Unsafe account accepted')

with tempfile.TemporaryDirectory(prefix='sr7420-accounts-') as temp:
    root = Path(temp); (root / 'etc').mkdir()
    template = root / 'template'
    public = 'root:$fixture:0:0:99999:7:::\n'
    template.write_text(public)
    passwd = 'root:x:0:0:root:/root:/bin/ash\nservice:x:123:123:service:/var/run:/bin/false\n'
    (root / 'etc/passwd').write_text(passwd)
    def write(token): (root / 'etc/shadow').write_text(public + 'service:' + token + ':0:0:99999:7:::\n')
    for token in ['x', '*', '!', '!$fixture']:
        write(token); assert verify_accounts(root, template)['non_login_service_accounts'] == ['service']
    for token in ['', '$fixture']:
        write(token); rejects(lambda: verify_accounts(root, template))
    write('x'); (root / 'etc/passwd').write_text(passwd.replace('/bin/false', '/bin/ash'))
    rejects(lambda: verify_accounts(root, template))
    (root / 'etc/passwd').write_text(passwd.replace(':123:123:', ':0:123:'))
    rejects(lambda: verify_accounts(root, template))
    (root / 'etc/passwd').write_text(passwd)
    (root / 'etc/shadow').write_text((root / 'etc/shadow').read_text().replace('$fixture', '$changed'))
    rejects(lambda: verify_accounts(root, template))
print('PASS public and non-login service account checks')
