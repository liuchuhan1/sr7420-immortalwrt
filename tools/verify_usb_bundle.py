#!/usr/bin/env python3
"""Verify actual USB release archives without booting or writing a device."""
import argparse, hashlib, io, json, posixpath, re, stat, struct, subprocess, tarfile, tempfile
from pathlib import Path, PurePosixPath
from build_usb_bundle import verify_accounts
from usb_artifacts import canonical, module_info, sha256


def contents(data):
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive:
            name = PurePosixPath(item.name)
            assert not name.is_absolute() and '..' not in name.parts and item.name not in result
            assert item.isfile() or item.isdir() or item.issym()
            assert item.uid == item.gid == 0 and item.uname == item.gname == '' and item.mtime == 0
            if item.isfile(): result[item.name] = archive.extractfile(item).read()
            elif item.issym(): result[item.name] = ('link', item.linkname)
    return result


def resolve(tree, name, seen=None):
    seen = set() if seen is None else seen
    assert name not in seen and name in tree, ('Missing or cyclic archive member', name)
    seen.add(name)
    value = tree[name]
    if isinstance(value, tuple):
        target = value[1]
        name = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(name), target))
        assert name != '..' and not name.startswith('../')
        return resolve(tree, name, seen)
    return value


def manifest(tree, data, prefix=''):
    count = 0
    for line in data.decode().splitlines():
        digest, name = line.split('  ', 1)
        assert re.fullmatch('[0-9a-f]{64}', digest)
        assert not name.startswith('/') and '..' not in PurePosixPath(name).parts
        assert hashlib.sha256(resolve(tree, prefix + name)).hexdigest() == digest, name
        count += 1
    assert count
    return count


def parse_cpio(data):
    result, offset = {}, 0
    while True:
        assert data[offset:offset+6] == b'070701'
        fields = [int(data[offset+6+i*8:offset+14+i*8], 16) for i in range(13)]
        mode, size, length = fields[1], fields[6], fields[11]
        assert fields[2] == fields[3] == 0 and 0 < length <= 4096
        raw = data[offset+110:offset+110+length]; assert raw[-1:] == b'\0'
        name = raw[:-1].decode(); assert not name.startswith('/') and '..' not in PurePosixPath(name).parts
        offset = (offset + 110 + length + 3) & ~3
        assert offset + size <= len(data)
        if name == 'TRAILER!!!': break
        assert name not in result
        result[name] = (mode, data[offset:offset+size])
        offset = (offset + size + 3) & ~3
    return result


def aarch64(data, executable=False, static=False):
    assert data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == 183
    if executable: assert struct.unpack_from('<H', data, 16)[0] in [2, 3]
    if static:
        offset = struct.unpack_from('<Q', data, 32)[0]
        size, count = struct.unpack_from('<HH', data, 54)
        assert size >= 56 and offset + size * count <= len(data)
        assert all(struct.unpack_from('<I', data, offset + i * size)[0] != 3 for i in range(count))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--module-audit', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--repository-key', type=Path, required=True)
    a = p.parse_args(); repo = Path(__file__).resolve().parents[1]
    report = json.loads((a.output / 'bundle-report.json').read_text())
    archive = a.output / 'sr7420-usb44-offline.tar.gz'
    launcher = a.output / 'sr7420-usb44-launcher.tar.gz'
    assert sha256(archive) == report['bundle_sha256'] and sha256(launcher) == report['launcher_sha256']
    payload, launch = contents(archive.read_bytes()), contents(launcher.read_bytes())
    counts = {'payload': manifest(payload, payload['bundle.sha256']),
              'boot': manifest(payload, payload['boot/boot.sha256'], 'boot/'),
              'launcher': manifest(launch, launch['launcher.sha256'])}
    root = contents(payload['rootfs.tar.gz'])
    counts['root'] = manifest(root, payload['root.sha256'])
    for name in ['etc/config/network', 'etc/config/wireless', 'usr/sbin/sr7420-ram-init', 'usr/sbin/sr7420-boot-guard']:
        assert root[name] == (repo / 'files' / name).read_bytes(), name
    with tempfile.TemporaryDirectory(prefix='sr7420-verify-usb-') as temp:
        temp = Path(temp); (temp / 'etc').mkdir()
        for name in ['passwd', 'shadow']: (temp / 'etc' / name).write_bytes(root['etc/' + name])
        accounts = verify_accounts(temp, repo / 'files/etc/shadow')
        record = next(x for x in root['etc/shadow'].decode().splitlines() if x.startswith('root:')).split(':')[1]
        parts = record.split('$'); assert parts[1] in ['1', '5', '6'] and len(parts) == 4
        calculated = subprocess.check_output(['openssl', 'passwd', '-' + parts[1], '-salt', parts[2], 'password'], text=True).strip()
        assert calculated == record, 'Default root password differs from public password'
        builtins = set(json.loads(a.module_audit.read_text())['builtin_module_names'])
        cpio = (a.output / 'bootstrap.cpio').read_bytes(); bootstrap = parse_cpio(cpio)
        assert bootstrap['init'][1] == (repo / 'installer/init-usb.sh').read_bytes()
        assert stat.S_ISCHR(bootstrap['dev/console'][0])
        loaded = set(builtins); module_count = 0
        for line in bootstrap['load-usb.sh'][1].decode().splitlines():
            if not line.startswith('/bin/busybox insmod '): continue
            name = line.split()[2].lstrip('/'); data = bootstrap[name][1]; aarch64(data)
            target = temp / Path(name).name; target.write_bytes(data); info = module_info(target)
            assert info['vermagic'].split()[0] == report['kernel_release']
            dependencies = {canonical(x) for x in info.get('depends', '').split(',') if x}
            assert dependencies <= loaded, (name, sorted(dependencies - loaded))
            loaded.add(canonical(info.get('name', target.stem))); module_count += 1
        required = {'usbcore','phy_generic','dwc3','dwc3_generic_plat','xhci_hcd','xhci_plat_hcd','usb_storage','scsi_mod','sd_mod','ext4'}
        assert required <= loaded
    image = payload['boot/Image']; assert image[56:60] == b'ARMd' and image.count(cpio) == 1
    assert hashlib.sha256(image).hexdigest() == report['image_sha256']
    aarch64(payload['boot/kexec'], executable=True, static=True)
    assert hashlib.sha256(payload['boot/kexec']).hexdigest() == report['kexec_sha256']
    assert root['etc/apk/keys/public-key.pem'] == a.repository_key.read_bytes()
    assert root['etc/apk/repositories.d/sr7420.list'].decode().strip() == report['kmod_index_url']
    assert report['kernel_abi'] in report['kmod_index_url']
    assert b'__BUNDLE_' not in launch['sr7420-usb.sh'] and payload['release-id'] == b'sr7420-usb44\n'
    assert launch['sr7420-usb.sh'] == (a.output / 'sr7420-usb.sh').read_bytes()
    assert report['bundle_sha256'].encode() in launch['sr7420-usb.sh']
    for name in root:
        assert not re.search(r'(?:^|/)(?:cal-pci-[^/]+|board-2)\.bin$', name), name
        if name.startswith(('etc/config/', 'etc/banner', 'etc/openwrt_release', 'etc/board.json', 'etc/sr7420', 'usr/lib/os-release')) and isinstance(root[name], bytes):
            assert b'sr1010' not in root[name].lower(), name
    result = {'passed': True, 'scope': 'offline artifact checks; no router boot or network test',
              'kernel_release': report['kernel_release'], 'kernel_abi_hash': report['kernel_abi'],
              'manifest_entries_checked': counts, 'bootstrap_modules_checked': module_count,
              'bootstrap_embedded_in_image': True, 'bootstrap_offset': image.find(cpio),
              'default_password_verified': True, 'accounts': accounts,
              'device_calibration_included': False, 'hardware_verified': False}
    a.report.write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result))


if __name__ == '__main__': main()
