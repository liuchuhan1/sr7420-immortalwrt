#!/usr/bin/env python3
"""Rebuild a static ARM64 kexec with the matching toolchain and bundle its source."""
import argparse, json, os, shutil, subprocess
from pathlib import Path
from usb_artifacts import archive_tree, run, sha256, write

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--topdir', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--jobs', type=int, default=8)
a = p.parse_args()
assert os.geteuid() != 0, 'Build as an ordinary user'
assert a.jobs > 0
source, top, output = a.source.resolve(), a.topdir.resolve(), a.output.resolve()
assert (source / 'configure').is_file() and (source / 'COPYING').is_file()
assert not output.exists()
assert not output.is_relative_to(source), 'Keep work and source directories separate'
for path in source.rglob('*'):
    if path.is_symlink():
        assert path.resolve().is_relative_to(source), 'Source contains an external symlink'
toolchains = list((top / 'staging_dir').glob('toolchain-aarch64_cortex-a53_gcc-*_musl'))
assert len(toolchains) == 1
cross = str(toolchains[0] / 'bin/aarch64-openwrt-linux-musl-')
env = os.environ.copy()
env['STAGING_DIR'] = str(top / 'staging_dir/target-aarch64_cortex-a53_musl')
env['SOURCE_DATE_EPOCH'] = '0'
env['LC_ALL'] = 'C'
env['PATH'] = str(top / 'staging_dir/host/bin') + os.pathsep + env.get('PATH', '')
output.mkdir(parents=True)
work = output / 'work'
shutil.copytree(source, work, symlinks=True, ignore=shutil.ignore_patterns('.git', '__pycache__'))
if (work / 'Makefile').is_file():
    run(['make', 'distclean'], cwd=work, env=env)
assert not list(work.rglob('*.o')) and not (work / 'config.log').exists()
# kexec distclean removes generated release files; retain them from this source.
for generated in ('configure', 'include/config.h.in'):
    assert (source / generated).is_file(), generated
    shutil.copy2(source / generated, work / generated)
recipe = """#!/bin/sh
# From a clean source root; pass the full cross-toolchain prefix.
set -eu
CROSS=${1:?usage: build-static.sh /path/to/aarch64-openwrt-linux-musl- [jobs]}
JOBS=${2:-8}
export LC_ALL=C SOURCE_DATE_EPOCH=0
export CC="${CROSS}gcc" LD="${CROSS}ld" AS="${CROSS}as"
export AR="${CROSS}ar" STRIP="${CROSS}strip" OBJCOPY="${CROSS}objcopy"
export CFLAGS="-Os -ffile-prefix-map=$(pwd)=kexec-tools -fdebug-prefix-map=$(pwd)=kexec-tools"
export LDFLAGS="-static -Wl,--build-id=none"
./configure --host=aarch64-openwrt-linux-musl --without-zlib --without-lzma --without-xen
make -j"$JOBS"
"""
write(work / 'build-static.sh', recipe, 0o755)
archive = output / 'kexec-tools-corresponding-source.tar.gz'
archive_tree(work, archive)
try:
    result = run(['sh', './build-static.sh', cross, str(a.jobs)], cwd=work, env=env)
except subprocess.CalledProcessError as error:
    write(output / 'build.log', (error.stdout or '') + (error.stderr or ''))
    raise
write(output / 'build.log', result.stdout + result.stderr)
binaries = [x for x in work.rglob('kexec') if x.is_file() and x.read_bytes()[:4] == b'\x7fELF']
assert len(binaries) == 1, 'Ambiguous kexec output'
binary = output / 'kexec'
shutil.copy2(binaries[0], binary)
run([cross + 'strip', '--strip-all', binary])
assert 'INTERP' not in run([cross + 'readelf', '-l', binary]).stdout
assert 'AArch64' in run([cross + 'readelf', '-h', binary]).stdout
shutil.copy2(work / 'COPYING', output / 'COPYING.kexec')
report = {'binary': binary.name, 'binary_sha256': sha256(binary),
          'binary_bytes': binary.stat().st_size, 'source': archive.name,
          'source_sha256': sha256(archive), 'license_sha256': sha256(output / 'COPYING.kexec'),
          'binary_built_from_supplied_source': True, 'static': True,
          'source_build_recipe': 'build-static.sh',
          'strip_command': 'aarch64-openwrt-linux-musl-strip --strip-all ' + binaries[0].relative_to(work).as_posix(),
          'hardware_verified': False}
write(output / 'kexec-report.json', json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
