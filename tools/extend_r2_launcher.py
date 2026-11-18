#!/usr/bin/env python3
"""Add optional stable mode and autostart without repacking the published r2 system."""
import argparse
import gzip
import hashlib
import io
import json
import posixpath
import tarfile
from pathlib import Path, PurePosixPath

from stable_payload import autostart_payload, stable_payload
from usb_artifacts import sha256


BASE_SHA = '4a5d5bcadd39282d393f4231409265e329043372fa5bff4bd359c131e80c3bb5'
BUNDLE_SHA = '0936aaac1e8b3762dda9a4114feb0f17d7b1e81017ec20d2d4cb5d6961460e71'
BUNDLE_URL = ('https://github.com/liuchuhan1/sr7420-immortalwrt/releases/download/'
              'usb44-r2-20261118/sr7420-usb44-offline.tar.gz')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(original, output):
    repo = Path(__file__).resolve().parents[1]
    original, output = Path(original), Path(output)
    raw = original.read_bytes()
    if digest(raw) != BASE_SHA:
        raise ValueError('The exact published r2 launcher is required')

    entries = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for info in archive:
            name = info.name
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts or path.as_posix() != name
                    or name in entries or not (info.isfile() or info.isdir() or info.issym())):
                raise ValueError(f'Invalid base archive entry: {name}')
            data = archive.extractfile(info).read() if info.isfile() else b''
            entries[name] = info, data

    def put(name, data, mode):
        for parent in reversed(PurePosixPath(name).parents):
            key = parent.as_posix()
            if key == '.':
                continue
            if key not in entries:
                info = tarfile.TarInfo(key)
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                entries[key] = info, b''
            elif not entries[key][0].isdir():
                raise ValueError(f'Not an archive directory: {key}')
        info = tarfile.TarInfo(name)
        info.mode, info.size = mode, len(data)
        entries[name] = info, data

    def file_data(name):
        seen = set()
        while name in entries and name not in seen:
            seen.add(name)
            info, data = entries[name]
            if info.isfile():
                return data
            if not info.issym():
                break
            name = posixpath.normpath(posixpath.join(posixpath.dirname(name), info.linkname))
        raise ValueError(f'Cannot resolve archive file: {name}')

    template = (repo / 'installer/sr7420-usb.sh.in').read_text(encoding='utf-8')
    script = template.replace('__BUNDLE_URL__', BUNDLE_URL).replace('__BUNDLE_SHA256__', BUNDLE_SHA).encode('utf-8')
    if b'__BUNDLE_' in script:
        raise ValueError('Unsubstituted bundle field')
    put('sr7420-usb.sh', script, 0o755)
    for directory, payload in (('policy', stable_payload(repo)), ('autostart', autostart_payload(repo))):
        for name, (data, mode) in payload.items():
            put(directory + '/' + name, data, mode)
    manifest = ''.join(f'{digest(file_data(name))}  {name}\n'
                       for name, (info, _) in sorted(entries.items())
                       if not info.isdir() and name != 'launcher.sha256')
    put('launcher.sha256', manifest.encode('ascii'), 0o644)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', filename='',
            mtime=0, compresslevel=6) as gz, tarfile.open(fileobj=gz, mode='w|',
            format=tarfile.PAX_FORMAT) as archive:
        for _, (info, data) in sorted(entries.items()):
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = 0
            info.pax_headers = {}
            archive.addfile(info, io.BytesIO(data) if info.isfile() else None)
    return {'base_launcher_sha256': BASE_SHA, 'system_bundle_sha256': BUNDLE_SHA,
            'system_bundle_repacked': False, 'launcher_sha256': sha256(output),
            'launcher_bytes': output.stat().st_size, 'installer_sha256': digest(script),
            'stock_autostart_backend': 'nativeC-loopback-telnet', 'hardware_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--r2-launcher', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.r2_launcher, args.output), indent=2))
