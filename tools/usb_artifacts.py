#!/usr/bin/env python3
"""Deterministic archives and dependency closure for the USB bootstrap."""
import gzip, hashlib, os, re, stat, struct, subprocess, tarfile
from pathlib import Path


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          capture_output=True, **kwargs)


def write(path, text, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))
    path.chmod(mode)


def canonical(name):
    return name.replace('-', '_')


def module_info(path):
    data = Path(path).read_bytes()
    # Search only .modinfo: executable strings can also contain name= and depends=.
    assert data[:6] == b'\x7fELF\x02\x01' and len(data) >= 64, 'Expected ELF64 little-endian module'
    offset = struct.unpack_from('<Q', data, 40)[0]
    entry_size, count, names_index = struct.unpack_from('<HHH', data, 58)
    assert entry_size >= 64 and count > 0 and names_index < count
    assert offset + entry_size * count <= len(data), 'Truncated ELF section table'
    def section(index):
        start = offset + entry_size * index
        name, section_type = struct.unpack_from('<II', data, start)
        file_offset, size = struct.unpack_from('<QQ', data, start + 24)
        if section_type == 8:  # SHT_NOBITS (.bss) occupies no bytes in the ELF file.
            return name, b''
        assert file_offset + size <= len(data), 'Truncated ELF section'
        return name, data[file_offset:file_offset + size]
    names = section(names_index)[1]
    matches = []
    for index in range(count):
        name, content = section(index)
        assert name < len(names)
        if names[name:].split(b'\0', 1)[0] == b'.modinfo':
            matches.append(content)
    assert len(matches) == 1, 'Missing or ambiguous .modinfo'
    data = matches[0]
    result = {}
    for key in ('depends', 'vermagic', 'name'):
        values = re.findall(rb'(?:^|\x00)' + key.encode() + rb'=([^\x00]*)\x00', data)
        if values:
            assert len(set(values)) == 1, ('ambiguous module metadata', key)
            result[key] = values[0].decode('ascii')
    assert 'vermagic' in result, ('not a loadable kernel module', str(path))
    return result


def module_closure(kernel, required, optional=()):
    """Return dependency-first module paths; builtins satisfy dependencies."""
    kernel = Path(kernel)
    builtin = {canonical(Path(x).stem) for x in
               (kernel / 'modules.builtin').read_text().splitlines()}
    available = {}
    for line in (kernel / 'modules.order').read_text().splitlines():
        # 6.18 lists .o link targets, whereas older kernels list .ko files.
        # kernel/configs is also a real source path, not an install prefix.
        rel = Path(line)
        if rel.suffix == '.o':
            rel = rel.with_suffix('.ko')
        path = kernel / rel
        if not path.is_file() and rel.as_posix().startswith('kernel/'):
            path = kernel / rel.as_posix().removeprefix('kernel/')
        key = canonical(path.stem)
        assert path.is_file(), ('missing built module', str(rel))
        assert key not in available, ('ambiguous module basename', key)
        available[key] = path
    order, done, visiting = [], set(), set()

    def visit(name):
        name = canonical(name)
        if name in builtin or name in done:
            return
        assert name in available, ('bootstrap module unavailable', name)
        assert name not in visiting, ('module dependency cycle', name)
        visiting.add(name)
        path = available[name]
        for child in filter(None, module_info(path).get('depends', '').split(',')):
            visit(child)
        visiting.remove(name)
        done.add(name)
        order.append(path)

    for name in required:
        visit(name)
    for name in optional:
        if canonical(name) in available or canonical(name) in builtin:
            visit(name)
    return order, sorted(builtin)


def elf_runtime(readelf, binaries, library_roots):
    """Resolve DT_NEEDED recursively without executing target-architecture ELF."""
    libraries = {}
    queue = list(map(Path, binaries))
    checked = set()
    while queue:
        path = queue.pop()
        resolved = path.resolve()
        if resolved in checked:
            continue
        checked.add(resolved)
        header = run([readelf, '-h', resolved]).stdout
        assert re.search(r'Machine:\s+AArch64', header), ('wrong ELF architecture', path.name)
        dynamic = run([readelf, '-d', resolved]).stdout
        for name in re.findall(r'Shared library: \[([^\]]+)\]', dynamic):
            assert '/' not in name and '..' not in name, ('invalid SONAME', name)
            if name in libraries:
                continue
            source = next((Path(root) / name for root in library_roots
                           if (Path(root) / name).is_file()), None)
            assert source, ('missing shared library', name, path.name)
            libraries[name] = source.resolve()
            queue.append(source)
    return libraries


def newc(entries):
    """Build a uid/gid-zero newc archive, including genuine device-node metadata."""
    output = bytearray()
    names = set()
    entries = list(entries)
    for ino, (name, data, mode, major, minor) in enumerate(
            entries + [('TRAILER!!!', b'', 0, 0, 0)], 1):
        assert name not in names and not name.startswith('/') and '..' not in Path(name).parts
        names.add(name)
        encoded = name.encode()
        fields = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded) + 1, 0]
        output += b'070701' + b''.join(f'{x:08x}'.encode() for x in fields) + encoded + b'\0'
        output += bytes(-len(output) % 4)
        output += data
        output += bytes(-len(output) % 4)
    output += bytes(-len(output) % 512)
    return bytes(output)


def archive_tree(source, destination, epoch=0):
    """Archive a private staging tree with stable order and no host identities."""
    source, destination = Path(source), Path(destination)
    with destination.open('wb') as raw, gzip.GzipFile(filename='', mode='wb',
            fileobj=raw, mtime=epoch, compresslevel=6) as compressed, \
            tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(source.rglob('*')):
            rel = path.relative_to(source).as_posix()
            info = archive.gettarinfo(str(path), arcname=rel)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = epoch
            info.pax_headers = {}
            assert info.isfile() or info.isdir() or info.issym(), ('unexpected special file', rel)
            if info.isfile():
                with path.open('rb') as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)


def manifest_tree(root, output, paths=None):
    root, output = Path(root), Path(output)
    paths = list(paths) if paths is not None else sorted(root.rglob('*'))
    lines = []
    for path in sorted(paths):
        if path == output or not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        assert not re.search(r'\s', name) and '..' not in name
        lines.append(f'{sha256(path)}  {name}\n')
    assert lines, 'Empty integrity manifest'
    write(output, ''.join(lines))
