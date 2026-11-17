#!/usr/bin/env python3
"""Offline checks for module ordering and actual initramfs/archive formats."""
import importlib.util, os, stat, struct, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from usb_artifacts import archive_tree, module_closure, module_info, newc, sha256


def fake_module(dependencies):
    names = b'\0.shstrtab\0.modinfo\0.noise\0'
    metadata = b'vermagic=6.18.60\0depends=' + dependencies.encode() + b'\0name=fixture\0'
    noise = b'name=unrelated-debug-string\0depends=not-a-real-dependency\0'
    header = bytearray(64)
    header[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHI', header, 16, 1, 183, 1)
    table_offset = 64 + len(names) + len(metadata) + len(noise)
    struct.pack_into('<Q', header, 40, table_offset)
    struct.pack_into('<HHHHHH', header, 52, 64, 0, 0, 64, 4, 1)
    def section(name, offset, size):
        row = bytearray(64)
        struct.pack_into('<II', row, 0, name, 1)
        struct.pack_into('<QQ', row, 24, offset, size)
        return bytes(row)
    return bytes(header) + names + metadata + noise + bytes(64) + section(1, 64, len(names)) + section(11, 64 + len(names), len(metadata)) + section(20, 64 + len(names) + len(metadata), len(noise))


def rejects(callback):
    try:
        callback()
    except AssertionError:
        return
    raise AssertionError('Invalid artifact unexpectedly accepted')


entries = [('dev', b'', 0o040755, 0, 0),
           ('dev/console', b'', 0o020600, 5, 1),
           ('bin/sh', b'busybox', 0o120777, 0, 0),
           ('init', b'#!/bin/sh\necho init\n', 0o100755, 0, 0)]
data = newc(entries)
assert len(data) % 512 == 0
pos, parsed = 0, []
while True:
    assert data[pos:pos+6] == b'070701'
    fields = [int(data[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
    assert fields[2:4] == [0, 0] and fields[5] == 0
    size, namesize = fields[6], fields[11]
    name = data[pos+110:pos+110+namesize]
    assert name[-1:] == b'\0'
    name = name[:-1].decode()
    pos = (pos + 110 + namesize + 3) & ~3
    body = data[pos:pos+size]
    pos = (pos + size + 3) & ~3
    if name == 'TRAILER!!!':
        break
    parsed.append((name, body, fields[1], fields[9], fields[10]))
assert parsed == entries
rejects(lambda: newc([('../escape', b'', 0o100644, 0, 0)]))
rejects(lambda: newc([entries[0], entries[0]]))

with tempfile.TemporaryDirectory(prefix='sr7420-artifacts-') as tmp:
    root = Path(tmp)
    kernel = root / 'kernel'
    (kernel / 'drivers').mkdir(parents=True)
    (kernel / 'modules.builtin').write_text('kernel/drivers/builtin.ko\n')
    (kernel / 'modules.order').write_text('drivers/core.ko\ndrivers/usb-storage.ko\n')
    for name, deps in [('core', 'builtin'), ('usb-storage', 'core')]:
        (kernel / 'drivers' / (name + '.ko')).write_bytes(
            fake_module(deps))
    assert module_info(kernel / 'drivers/core.ko')['name'] == 'fixture'
    order, _ = module_closure(kernel, ['usb_storage'])
    assert [p.stem for p in order] == ['core', 'usb-storage']
    # Real 6.18 modules.order uses .o and includes the native kernel/ directory.
    (kernel / 'kernel').mkdir()
    (kernel / 'kernel/configs.ko').write_bytes(fake_module(''))
    (kernel / 'modules.order').write_text('kernel/configs.o\ndrivers/core.o\ndrivers/usb-storage.o\n')
    order, _ = module_closure(kernel, ['configs', 'usb_storage'])
    assert [p.relative_to(kernel).as_posix() for p in order] == [
        'kernel/configs.ko', 'drivers/core.ko', 'drivers/usb-storage.ko']
    rejects(lambda: module_closure(kernel, ['not-built']))
    (kernel / 'drivers/core.ko').write_bytes(fake_module('usb_storage'))
    rejects(lambda: module_closure(kernel, ['core']))
    source = root / 'tree'
    source.mkdir()
    (source / 'hello').write_text('deterministic\n')
    os.symlink('hello', source / 'link')
    archive_tree(source, root / 'one.tar.gz')
    os.utime(source / 'hello', (2000000000, 2000000000))
    archive_tree(source, root / 'two.tar.gz')
    assert sha256(root / 'one.tar.gz') == sha256(root / 'two.tar.gz')
print('newc headers/padding/device nodes, deterministic tar, module dependency ordering and fail-closed checks passed')
