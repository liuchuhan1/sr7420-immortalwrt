"""Build the same opt-in policy payload for both USB launcher builders."""
import hashlib


POLICY_FILES = ('etc/init.d/sr7420-usb-policy', 'usr/sbin/sr7420-usb-policy')


def stable_payload(repo):
    result = {}
    manifest = []
    for name in POLICY_FILES:
        data = (repo / 'installer/policy' / name).read_bytes()
        if not data.startswith(b'#!/bin/sh') or b'\r' in data:
            raise ValueError(f'Policy must be an LF shell script: {name}')
        result[name] = (data, 0o755)
        manifest.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    result['policy.sha256'] = (''.join(manifest).encode('ascii'), 0o644)
    return result
