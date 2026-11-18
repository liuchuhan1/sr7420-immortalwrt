#!/usr/bin/env python3
"""Reject a byte-identical boot tool when its archive execute mode is lost."""
import io, sys, tarfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from verify_usb_bundle import contents

def archive(mode, name='boot/kexec', kind=tarfile.REGTYPE):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w:gz') as output:
        member = tarfile.TarInfo(name)
        member.mode, member.type = mode, kind
        if kind == tarfile.REGTYPE:
            data = b'\x7fELF-identical-tool-bytes'
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
        else:
            member.linkname = 'elsewhere'
            output.addfile(member)
    return result.getvalue()

valid = archive(0o755)
assert contents(valid, executables=('boot/kexec',))['boot/kexec'].startswith(b'\x7fELF')
for invalid in [archive(0o644), archive(0o755, name='other'), archive(0o777, kind=tarfile.SYMTYPE)]:
    try:
        contents(invalid, executables=('boot/kexec',))
    except AssertionError:
        pass
    else:
        raise AssertionError('Missing, non-executable or indirect boot tool was accepted')
# Default callers still inspect archives that contain ordinary data files.
assert contents(archive(0o644)) == contents(valid)
print('Executable archive members checked: byte-identical 0644 tools, missing tools and symlinks rejected')
