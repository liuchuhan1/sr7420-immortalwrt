#!/usr/bin/env python3
"""Audit selected in-tree kmod FILES against built modules and builtin records."""
import argparse, glob, json, os, re, subprocess, tempfile
from pathlib import Path

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--topdir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    source = a.topdir.resolve()
    kernels = [k for k in (source / 'build_dir').glob('target-*/linux-zte_zx279133/linux-*') if (k / '.config').is_file()]
    assert len(kernels) == 1
    kernel = kernels[0]
    release = (kernel / 'include/config/kernel.release').read_text().strip()
    patchver = '.'.join(release.split('.')[:2])
    selected = set(re.findall(r'^CONFIG_PACKAGE_(kmod-[^=]+)=[ym]$', (source / '.config').read_text(), re.M))
    builtins = {x.removeprefix('kernel/') for x in (kernel / 'modules.builtin').read_text().splitlines()}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sr7420-files-', dir=a.output.parent) as tmp:
        temporary = Path(tmp)
        text = (source / 'include/kernel.mk').read_text()
        needle = '  $$(IPKG_kmod-$(1)): $$(wildcard $$(call version_filter,$$(FILES)))'
        assert text.count(needle) == 1
        text = text.replace(needle, needle + '\n  $(info SR7420_RECORD\tkmod-$(1)\t$(strip $(call version_filter,$(FILES)))\t$(strip $(DEPENDS))\t$(strip $(KCONFIG)))')
        (temporary / 'kernel.mk').write_text(text)
        text = (source / 'package/kernel/linux/Makefile').read_text().replace('include $(INCLUDE_DIR)/kernel.mk', 'include ' + str(temporary / 'kernel.mk'))
        (temporary / 'linux.mk').write_text(text + '\n.PHONY: __sr7420_audit\n__sr7420_audit:\n\t@:\n')
        env = os.environ.copy()
        env['STAGING_DIR'] = str(source / 'staging_dir/target-aarch64_cortex-a53_musl')
        env['PATH'] = str(source / 'staging_dir/host/bin') + ':' + env['PATH']
        q = subprocess.run(['make', '-s', '-C', str(source / 'package/kernel/linux'), '-f', str(temporary / 'linux.mk'),
            'TOPDIR=' + str(source), '__sr7420_audit', 'LINUX_DIR=' + str(kernel), 'KERNEL_BUILD_DIR=' + str(kernel.parent),
            'KERNEL_PATCHVER=' + patchver, 'LINUX_VERSION=' + release, 'BOARD=zte', 'SUBTARGET=zx279133', 'ARCH=aarch64'],
            env=env, capture_output=True, text=True, check=True)
    records, missing = [], []
    for line in q.stdout.splitlines():
        if not line.startswith('SR7420_RECORD\t'):
            continue
        _, name, files, depends, kconfig = line.split('\t', 4)
        if name not in selected:
            continue
        rec = {'package': name, 'kconfig': kconfig, 'depends': depends, 'modules': [], 'builtin': []}
        for pattern in files.split():
            relative = Path(pattern).relative_to(kernel).as_posix()
            matches = [Path(x) for x in glob.glob(pattern) if Path(x).is_file()]
            if matches:
                rec['modules'] += [x.relative_to(kernel).as_posix() for x in matches]
            elif relative in builtins:
                rec['builtin'].append(relative)
            else:
                missing.append({'package': name, 'file': relative, 'kconfig': kconfig})
        records.append(rec)
    result = {'passed': not missing, 'kernel_release': release, 'packages_checked': len(records),
        'scope': 'In-tree KernelPackage FILES; external packages require the APK module audit',
        'missing_files': missing, 'records': records}
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ['passed', 'packages_checked', 'missing_files']}))
    raise SystemExit(0 if result['passed'] else 1)

if __name__ == '__main__':
    main()
