#!/usr/bin/env python3
"""Inspect packaged kernel modules and their global dependency closure."""
import argparse, json, shutil, struct, subprocess, tempfile
from pathlib import Path
from apk_metadata import sha256
from usb_artifacts import canonical, module_info

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--topdir', type=Path, required=True)
    p.add_argument('--selection-report', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    source = a.topdir.resolve()
    selection = json.loads(a.selection_report.read_text())
    assert selection['compiled'] and not selection['selected_without_apk']
    kernels = [k for k in (source / 'build_dir').glob('target-*/linux-*/linux-*') if (k / '.config').is_file()]
    assert len(kernels) == 1
    kernel = kernels[0]
    release = (kernel / 'include/config/kernel.release').read_text().strip()
    builtins = {canonical(Path(line).stem) for line in (kernel / 'modules.builtin').read_text().splitlines()}
    modules, empty, failures = [], [], []
    with tempfile.TemporaryDirectory(prefix='sr7420-module-audit-') as tmp:
        destination = Path(tmp) / 'payload'
        for record in selection['package_records']:
            if record['name'] == 'kernel':
                continue
            package = source / 'bin' / record['file']
            assert sha256(package) == record['sha256'], 'APK changed since metadata report'
            if destination.exists():
                shutil.rmtree(destination)
            destination.mkdir()
            subprocess.run([str(source / 'staging_dir/host/bin/apk'), '--allow-untrusted',
                'extract', '--no-chown', '--destination', str(destination), str(package)],
                check=True, capture_output=True, timeout=60)
            paths = sorted(destination.rglob('*.ko'))
            if not paths:
                empty.append(record['name'])
            for path in paths:
                assert not path.is_symlink()
                data = path.read_bytes()
                relative = path.relative_to(destination).as_posix()
                assert data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == 183, 'Non-AArch64 module'
                info = module_info(path)
                item = {'package': record['name'], 'file': relative, 'name': canonical(info.get('name', path.stem)),
                    'vermagic': info['vermagic'], 'depends': [canonical(x) for x in info.get('depends', '').split(',') if x]}
                if info['vermagic'].split()[0] != release:
                    failures.append({'package': record['name'], 'file': relative, 'reason': 'wrong_vermagic'})
                modules.append(item)
    available = builtins | {item['name'] for item in modules}
    for item in modules:
        for dependency in item['depends']:
            if dependency not in available:
                failures.append({'package': item['package'], 'file': item['file'], 'missing_module': dependency})
    result = {'passed': not failures, 'kernel_abi': selection['kernel_abi'], 'kernel_release': release,
        'packages_inspected': len(selection['package_records']) - 1, 'module_files': len(modules),
        'packages_without_ko': empty, 'builtin_module_names': sorted(builtins), 'modules': modules,
        'failures': failures, 'scope': 'Global dependency closure and architecture; not hardware or per-package installation testing'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ['passed', 'packages_inspected', 'module_files', 'failures']}))
    raise SystemExit(0 if result['passed'] else 1)

if __name__ == '__main__':
    main()
