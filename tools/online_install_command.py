#!/usr/bin/env python3
"""Emit one stock-shell command with an embedded GitHub raw-file trust anchor.

No curl --insecure, unpinned branch, credentials or device serial are emitted.
The 2026 stock userland has neither a CA bundle nor a SHA checksum utility.
"""
from pathlib import Path
import argparse, re, shlex


def command(ref, arguments):
    if not re.fullmatch(r'[0-9a-f]{40}', ref):
        raise ValueError('Use a published immutable Git commit SHA')
    ca_file = Path(__file__).resolve().parents[1] / 'installer/github-bootstrap-ca.crt'
    ca = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', ca_file.read_text(encoding='ascii'), re.S)[-1] + '\n'
    ca = ca.replace('\n', r'\n')
    url = ('https://raw.githubusercontent.com/liuchuhan1/sr7420-immortalwrt/'
           + ref + '/installer/sr7420-install-online.sh')
    script = ('set -eu; umask 077; d=/var/sr7420-fetch.$$; mkdir -m 700 "$d"; '
              'trap \'rm -f "$d/ca.pem" "$d/install.sh"; rmdir "$d"\' EXIT; '
              'printf "%b" ' + shlex.quote(ca) + ' >"$d/ca.pem"; '
              'curl --fail --location --proto "=https" --proto-redir "=https" '
              '--cacert "$d/ca.pem" --retry 2 --connect-timeout 10 --max-time 120 '
              '--max-filesize 32768 -o "$d/install.sh" ' + shlex.quote(url) + '; '
              'sh "$d/install.sh" "$@"')
    return 'sh -c ' + shlex.quote(script) + ' -- ' + shlex.join(arguments)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True, help='Published source commit SHA')
    parser.add_argument('--install', action='store_true', help='Authorize erasure of the sole eligible USB')
    parser.add_argument('--boot', action='store_true', help='Switch to USB after installing (network interruption)')
    args = parser.parse_args()
    if args.boot and not args.install:
        parser.error('--boot requires --install')
    options = ['install', '--erase-single-usb'] if args.install else ['detect']
    if args.boot:
        options.append('--boot')
    print(command(args.ref, options))
