#!/usr/bin/env python3
"""Reject stale ABIs and ambiguous packages before constructing a module feed."""
import sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from apk_metadata import collect_kmods, parse_adbdump


def rejects(callback):
    try:
        callback()
    except AssertionError:
        return
    raise AssertionError('Malformed package metadata unexpectedly accepted')


text = """#%SCHEMA: 676B6370
info:
  name: kmod-test
  version: 6.18.60-r1
  arch: aarch64_cortex-a53
  depends: # 2 items
    - libc
    - kernel=6.18.60~aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-r1
paths: # 0 items
"""
meta = parse_adbdump(text)
assert meta['name'] == 'kmod-test'
assert meta['kernel_dependencies'] == ['6.18.60~aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-r1']
rejects(lambda: parse_adbdump(text.replace('  arch:', '  architecture:')))
rejects(lambda: parse_adbdump(text.replace('  name:', '  name: duplicate\n  name:')))
rejects(lambda: parse_adbdump('paths: # 0 items\n'))

with tempfile.TemporaryDirectory(prefix='sr7420-apk-') as temporary:
    root = Path(temporary)
    kernel = root / 'kernel'
    (kernel / 'include/config').mkdir(parents=True)
    (kernel / 'include/config/kernel.release').write_text('6.18.60\n')
    (kernel / '.vermagic').write_text('a' * 32)
    packages = root / 'bin/targets/zte/zx279133/packages'
    packages.mkdir(parents=True)
    abi = '6.18.60~' + 'a' * 32 + '-r1'
    arch = 'aarch64_cortex-a53'
    metadata = {}
    def add(filename, name, version, dependencies, architecture=arch):
        (packages / filename).write_bytes(filename.encode())
        metadata[filename] = {'name': name, 'version': version, 'arch': architecture,
                              'kernel_dependencies': dependencies}
    add('kernel-current.apk', 'kernel', abi, [])
    add('kernel-stale.apk', 'kernel', '6.18.60~' + 'b' * 32 + '-r1', [])
    add('kmod-good-1.apk', 'kmod-good', '6.18.60-r1', [abi])
    add('kmod-stale-1.apk', 'kmod-stale', '6.18.60-r1', ['obsolete'])
    add('kmod-foreign-1.apk', 'kmod-foreign', '6.18.60-r1', [abi], 'x86_64')
    add('kmod-unselected-1.apk', 'kmod-unselected', '6.18.60-r1', [abi])
    selected = {'kmod-good': 'm', 'kmod-stale': 'm', 'kmod-foreign': 'm'}
    with patch('apk_metadata.read_apk', side_effect=lambda apk, path: metadata[path.name]):
        result = collect_kmods(root, kernel, selected)
        assert {x['name'] for x in result['package_records']} == {'kernel', 'kmod-good'}
        assert len(result['ignored_apks']) == 4
        assert not result['ambiguous_packages'] and not result['invalid_apks']
        add('kmod-good-2.apk', 'kmod-good', '6.18.60-r2', [abi])
        result = collect_kmods(root, kernel, selected)
        assert result['ambiguous_packages'] == ['kmod-good']
        assert 'kmod-good' not in {x['name'] for x in result['package_records']}
print('APK metadata validation, stale ABI/architecture filtering, and duplicate rejection passed')
