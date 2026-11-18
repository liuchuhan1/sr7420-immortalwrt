"""Build the same opt-in payloads for both USB launcher builders."""
import hashlib


POLICY_FILES = ('etc/init.d/sr7420-usb-policy', 'usr/sbin/sr7420-usb-policy')
AUTOSTART_FILES = ('guest-config.sh', 'guest.sh', 'host.sh', 'manage.sh')


def _payload(directory, files, manifest_name):
    result = {}
    manifest = []
    for name in files:
        data = (directory / name).read_bytes()
        if not data.startswith(b'#!/bin/sh') or b'\r' in data:
            raise ValueError(f'Payload must be an LF shell script: {name}')
        result[name] = (data, 0o755)
        manifest.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    result[manifest_name] = (''.join(manifest).encode('ascii'), 0o644)
    return result


def stable_payload(repo):
    return _payload(repo / 'installer/policy', POLICY_FILES, 'policy.sha256')


def autostart_payload(repo):
    return _payload(repo / 'installer/autostart', AUTOSTART_FILES, 'autostart.sha256')
