#!/usr/bin/env python3
"""Build a USB-only development bundle; never create an OEM flashing container."""
import argparse, json, os, re, shutil, subprocess, time
from pathlib import Path
from luci_radio_labels import patch_file, patch_header_file
from usb_artifacts import (archive_tree, elf_runtime, manifest_tree, module_closure,
                           newc, run, sha256, write)


def verify_accounts(root, template):
    """Preserve public accounts exactly; allow only non-login package users."""
    def records(path, width):
        rows = [line.split(':') for line in path.read_text().splitlines()]
        assert all(len(row) == width and row[0] for row in rows), 'Malformed account database'
        result = {row[0]: row for row in rows}
        assert len(result) == len(rows), 'Duplicate account name'
        return result
    actual, expected = records(root / 'etc/shadow', 9), records(template, 9)
    assert 'root' in expected
    for name, row in expected.items():
        assert actual.get(name) == row, ('Public account changed', name)
    passwd = records(root / 'etc/passwd', 7)
    assert passwd.get('root', ['', '', ''])[2] == '0', 'Root UID changed'
    for name in sorted(actual.keys() - expected.keys()):
        row, account = actual[name], passwd.get(name)
        assert account and account[2].isdigit() and int(account[2]) != 0, ('Invalid service UID', name)
        assert account[-1] in ['/bin/false', '/sbin/nologin', '/usr/sbin/nologin'], ('Service shell permits login', name)
        assert row[1] and (row[1][0] in ['!', '*'] or row[1] == 'x'), ('Service password permits login', name)
    assert not any(row[2] == '0' and name != 'root' for name, row in passwd.items()), 'Additional root UID'
    assert passwd.keys() == actual.keys(), 'Passwd/shadow account mismatch'
    return {'public_accounts': sorted(expected), 'non_login_service_accounts': sorted(actual.keys() - expected.keys())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topdir', type=Path, required=True)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--kexec', type=Path, required=True)
    parser.add_argument('--kexec-source', type=Path, required=True)
    parser.add_argument('--kexec-license', type=Path, required=True)
    parser.add_argument('--kexec-sha256', required=True)
    parser.add_argument('--bundle-url', required=True)
    parser.add_argument('--kmod-index-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    assert os.geteuid() != 0, 'Build as the ordinary OpenWrt build user'
    assert args.bundle_url.startswith('https://'), 'Online release URL must use HTTPS'
    assert args.kmod_index_url.startswith('https://'), 'Kmod repository must use HTTPS'
    assert sha256(args.kexec) == args.kexec_sha256, 'Reviewed kexec binary hash required'
    assert args.kexec_source.is_file(), 'Corresponding kexec source must accompany its binary'
    assert args.kexec_license.is_file(), 'kexec GPL license must accompany its binary'
    source, output = args.topdir.resolve(), args.output.resolve()
    repo = Path(__file__).resolve().parents[1]
    assert not output.exists(), 'Use a new output directory'
    kernel_dirs = [x for x in (source / 'build_dir').glob('target-*/linux-zte_zx279133/linux-*')
                   if (x / '.config').is_file()]
    assert len(kernel_dirs) == 1
    kernel = kernel_dirs[0]
    version = (kernel / 'include/config/kernel.release').read_text().strip()
    abi = (kernel / '.vermagic').read_text().strip()
    toolchains = list((source / 'staging_dir').glob('toolchain-aarch64_cortex-a53_gcc-*_musl'))
    assert len(toolchains) == 1
    cross = toolchains[0] / 'bin/aarch64-openwrt-linux-musl-'
    readelf = str(cross) + 'readelf'
    env = os.environ.copy()
    env.update(STAGING_DIR=str(source / 'staging_dir/target-aarch64_cortex-a53_musl'),
               KBUILD_BUILD_USER='builder', KBUILD_BUILD_HOST='sr7420')
    config = (kernel / '.config').read_text()
    for symbol in ['PROC_FS', 'SYSFS', 'DEVTMPFS', 'DEVMEM', 'BINFMT_ELF', 'BLK_DEV_INITRD', 'MSDOS_PARTITION']:
        assert f'CONFIG_{symbol}=y' in config, ('bootstrap prerequisite must be builtin', symbol)
    assert (args.rootfs / 'sbin/procd').is_file() and (args.rootfs / 'bin/busybox').is_file()
    accounts = verify_accounts(args.rootfs, repo / 'files/etc/shadow')
    for relative in ['etc/config/network', 'etc/config/wireless', 'usr/sbin/sr7420-ram-init',
                     'usr/sbin/sr7420-boot-guard', 'usr/sbin/sr7420-usb-confirm',
                     'lib/preinit/81_sr7420_usb_root']:
        assert (args.rootfs / relative).read_bytes() == (repo / 'files' / relative).read_bytes(), relative
    output.mkdir(parents=True)
    shutil.copy2(args.kexec_source, output / 'kexec-tools-corresponding-source.tar.gz')
    shutil.copy2(args.kexec_license, output / 'COPYING.kexec')
    root = output / 'rootfs'
    shutil.copytree(args.rootfs, root, symlinks=True)
    for pattern in ['etc/dropbear/*_host_key', 'etc/dropbear/authorized_keys', 'root/.ssh/*',
                    'lib/firmware/ath12k/**/cal-pci-*', 'lib/firmware/ath12k/**/board-2.bin']:
        assert not list(root.glob(pattern)), ('private/device-specific material in clean root', pattern)
    assert not any((root / 'lib/firmware/qcn9224').glob('*'))
    assert abi in args.kmod_index_url and args.kmod_index_url.endswith('/packages.adb'), 'Kmod index must pin this kernel ABI'
    key = source / 'public-key.pem'
    assert key.is_file() and (root / 'etc/apk/keys/public-key.pem').read_bytes() == key.read_bytes(), 'Image and repository signing keys must match'
    feeds = root / 'etc/apk/repositories.d'
    distribution = feeds / 'distfeeds.list'
    assert distribution.is_file()
    # This custom board's kernel packages come from its own signed build.
    lines = [line for line in distribution.read_text().splitlines()
             if '/targets/zte/zx279133/' not in line]
    write(distribution, '\n'.join(lines) + '\n')
    write(feeds / 'sr7420.list', args.kmod_index_url + '\n')
    write(root / 'etc/sr7420-usb-release', 'sr7420-usb44\n')
    payload, boot, tools = output / 'payload', output / 'payload/boot', output / 'payload/tools'
    for directory in [boot, tools / 'bin', tools / 'lib']:
        directory.mkdir(parents=True, exist_ok=True)
    runtime = repo / 'build/runtime'
    for name in ['sha256', 'pci-quiesce', 'quiesce-check', 'stock-import']:
        assert (runtime / name).is_file(), 'Run tools/build_runtime.py first'
    libraries_at = [root / 'lib', root / 'usr/lib', source / 'staging_dir/target-aarch64_cortex-a53_musl/lib',
                    source / 'staging_dir/target-aarch64_cortex-a53_musl/usr/lib']
    binaries = {}
    for name in ['sfdisk', 'mke2fs', 'blkid', 'e2fsck', 'curl']:
        candidates = [p for directory in ['sbin', 'usr/sbin', 'bin', 'usr/bin']
                      for p in [root / directory / name] if p.is_file()]
        if not candidates:
            candidates = list((source / 'staging_dir/target-aarch64_cortex-a53_musl').glob('usr/*/' + name))
        assert len(candidates) == 1, ('missing or ambiguous utility', name)
        binaries[name] = candidates[0]
    libraries = elf_runtime(readelf, binaries.values(), libraries_at)
    for name, path in binaries.items():
        shutil.copy2(path.resolve(), tools / 'bin' / name)
    for name, path in libraries.items():
        shutil.copy2(path, tools / 'lib' / name)
    assert (tools / 'lib/libc.so').is_file()
    os.symlink('libc.so', tools / 'lib/ld-musl-aarch64.so.1')
    certificates = root / 'etc/ssl/certs/ca-certificates.crt'
    assert certificates.is_file()
    shutil.copy2(certificates, tools / 'ca-certificates.crt')
    write(tools / 'mke2fs.conf', '''[defaults]
 base_features = sparse_super,large_file,filetype,resize_inode,dir_index,ext_attr
 default_mntopts = acl,user_xattr
 enable_periodic_fsck = 0
 blocksize = 4096
 inode_size = 256
 inode_ratio = 16384
[fs_types]
 ext4 = {
 features = has_journal,extent,huge_file,flex_bg,metadata_csum,64bit,dir_nlink,extra_isize
 }
''')
    for name in ['sha256', 'stock-import']:
        shutil.copy2(runtime / name, payload / name)
    shutil.copy2(runtime / 'pci-quiesce', boot / 'pci-quiesce')
    shutil.copy2(args.kexec, boot / 'kexec')
    assert 'INTERP' not in run([readelf, '-l', boot / 'kexec']).stdout, 'Use a static kexec binary'
    patch_file(root / 'www/luci-static/resources/network.js')
    patch_header_file(root / 'usr/share/ucode/luci/template/header.ut')
    # Only immutable runtime files are checked on subsequent boots. UCI defaults,
    # passwords and normal configuration may legitimately change after first boot.
    immutable = [p for p in root.rglob('*') if p.is_file() and any(
        p.relative_to(root).as_posix().startswith(prefix) for prefix in
        ['bin/', 'sbin/', 'usr/bin/', 'usr/sbin/', 'lib/modules/', 'lib/lib', 'usr/lib/lib'])]
    manifest_tree(root, payload / 'root.sha256', immutable)
    archive_tree(root, payload / 'rootfs.tar.gz')
    # Resolve USB/SCSI/ext4 modules before switching to the USB root filesystem.
    modules, builtins = module_closure(kernel,
        ['usbcore', 'phy_generic', 'dwc3', 'dwc3_generic_plat', 'xhci_hcd', 'xhci_plat_hcd', 'usb_storage', 'scsi_mod', 'sd_mod', 'ext4'], ['uas'])
    scratch = output / 'bootstrap'
    scratch.mkdir()
    entries = [(name, b'', 0o040755, 0, 0) for name in
               ['bin', 'sbin', 'lib', 'lib/modules', 'lib/modules/' + version, 'dev', 'proc', 'sys', 'new_root']]
    bootstrap_bins = [root / 'bin/busybox', root / 'sbin/kmodloader']
    for name, path in elf_runtime(readelf, bootstrap_bins, libraries_at).items():
        entries.append(('lib/' + name, path.read_bytes(), 0o100755, 0, 0))
    entries += [('bin/busybox', bootstrap_bins[0].read_bytes(), 0o100755, 0, 0),
                ('sbin/kmodloader', bootstrap_bins[1].read_bytes(), 0o100755, 0, 0),
                ('sbin/insmod', b'kmodloader', 0o120777, 0, 0),
                ('lib/ld-musl-aarch64.so.1', b'libc.so', 0o120777, 0, 0),
                ('bin/sh', b'busybox', 0o120777, 0, 0),
                ('init', (repo / 'installer/init-usb.sh').read_bytes(), 0o100755, 0, 0),
                ('dev/console', b'', 0o020600, 5, 1), ('dev/null', b'', 0o020600, 1, 3)]
    commands = ['#!/bin/sh', '# Dependency-first USB root modules from this exact build.']
    for module in modules:
        target = scratch / module.name
        shutil.copy2(module, target)
        run([str(cross) + 'strip', '--strip-debug', target])
        entries.append(('lib/modules/' + version + '/' + target.name, target.read_bytes(), 0o100644, 0, 0))
        commands.append('if output=$(/sbin/insmod /lib/modules/' + version + '/' + target.name + ' 2>&1); then :; else '
                        'echo "<0>SR7420_STD: USB44 MODULE_FAILED ' + target.name + ': $output" >/dev/kmsg; return 1; fi')
    commands.append('return 0')
    entries.append(('load-usb.sh', ('\n'.join(commands) + '\n').encode(), 0o100755, 0, 0))
    cpio = newc(entries)
    write(scratch / 'module-order.json', json.dumps([p.name for p in modules], indent=2) + '\n')
    (output / 'bootstrap.cpio').write_bytes(cpio)
    # Standard OpenWrt initramfs builds change only INITRAMFS_* configuration.
    # Keep all functional kernel symbols and the package ABI unchanged.
    cpio_path = kernel / 'usr/sr7420-bootstrap.cpio'
    assert not cpio_path.exists()
    cpio_path.write_bytes(cpio)
    make = ['make', '-C', kernel, 'ARCH=arm64', 'CROSS_COMPILE=' + str(cross),
            'KERNELRELEASE=' + version, 'LOCALVERSION=']
    try:
        updated = re.sub(r'^CONFIG_INITRAMFS_SOURCE=.*$',
            'CONFIG_INITRAMFS_SOURCE="usr/sr7420-bootstrap.cpio"', config, flags=re.M)
        assert updated != config
        (kernel / '.config').write_text(updated)
        run(make + ['olddefconfig'], env=env)
        actual = (kernel / '.config').read_text()
        meaningful = lambda x: {v for v in x.splitlines()
                               if re.match(r'CONFIG_[A-Z0-9_]+=[ym]$', v) and 'CONFIG_INITRAMFS_' not in v}
        assert meaningful(config) == meaningful(actual), 'Bootstrap would change the kernel module ABI'
        assert (kernel / '.vermagic').read_text().strip() == abi
        run(make + ['-j' + str(args.jobs), 'Image'], env=env)
        shutil.copy2(kernel / 'arch/arm64/boot/Image', boot / 'Image')
        assert (boot / 'Image').read_bytes().count(cpio) == 1, 'Kernel does not contain the exact reviewed USB bootstrap'
    finally:
        (kernel / '.config').write_text(config)
        cpio_path.unlink(missing_ok=True)
    dts = source / 'target/linux/zte/dts/zx279133-sr7420-warmram.dts'
    preprocessed = run([str(cross) + 'gcc', '-E', '-P', '-x', 'assembler-with-cpp', '-undef',
        '-D__DTS__', '-nostdinc', '-I' + str(kernel / 'scripts/dtc/include-prefixes'),
        '-I' + str(kernel / 'arch/arm64/boot/dts'), '-I' + str(dts.parent), dts]).stdout
    run([kernel / 'scripts/dtc/dtc', '-I', 'dts', '-O', 'dtb', '-o', boot / 'board-template.dtb'], input=preprocessed)
    shutil.copy2(payload / 'root.sha256', boot / 'root.sha256')
    manifest_tree(boot, boot / 'boot.sha256')
    write(payload / 'release-id', 'sr7420-usb44\n')
    manifest_tree(payload, payload / 'bundle.sha256')
    bundle = output / 'sr7420-usb44-offline.tar.gz'
    archive_tree(payload, bundle)
    assert bundle.stat().st_size <= 64 * 1024 * 1024, 'Increase/retest RAM budget before publishing a larger bundle'
    script = (repo / 'installer/sr7420-usb.sh.in').read_text().replace(
        '__BUNDLE_URL__', args.bundle_url).replace('__BUNDLE_SHA256__', sha256(bundle))
    assert '__BUNDLE_' not in script
    write(output / 'sr7420-usb.sh', script, 0o755)
    # The stock system may have neither a TLS downloader nor the hash applet.
    # Ship a separate launcher runtime, available before downloading the bundle.
    launcher = output / 'launcher'
    (launcher / 'tools/bin').mkdir(parents=True)
    shutil.copy2(output / 'sr7420-usb.sh', launcher / 'sr7420-usb.sh')
    shutil.copy2(runtime / 'sha256', launcher / 'sha256')
    shutil.copytree(tools / 'lib', launcher / 'tools/lib', symlinks=True)
    shutil.copy2(tools / 'bin/curl', launcher / 'tools/bin/curl')
    shutil.copy2(tools / 'ca-certificates.crt', launcher / 'tools/ca-certificates.crt')
    for name in ['sr7420-usb-autostart.sh', 'sr7420-usb-disable.sh']:
        shutil.copy2(repo / 'installer' / name, launcher / name)
        (launcher / name).chmod(0o755)
    manifest_tree(launcher, launcher / 'launcher.sha256')
    launcher_archive = output / 'sr7420-usb44-launcher.tar.gz'
    archive_tree(launcher, launcher_archive)
    report = {'release': 'sr7420-usb44', 'kernel_release': version, 'kernel_abi': abi,
        'kmod_index_url': args.kmod_index_url, 'repository_public_key_sha256': sha256(key),
        'bootstrap_modules': [p.name for p in modules], 'tool_libraries': sorted(libraries),
        'bootstrap_cpio_bytes': len(cpio), 'bundle_bytes': bundle.stat().st_size,
        'bundle_sha256': sha256(bundle), 'kexec_sha256': sha256(args.kexec),
        'kexec_source_sha256': sha256(args.kexec_source),
        'kexec_license_sha256': sha256(args.kexec_license),
        'launcher_bytes': launcher_archive.stat().st_size, 'launcher_sha256': sha256(launcher_archive),
        'image_sha256': sha256(boot / 'Image'), 'accounts': accounts,
        'hardware_verified': False, 'oem_upload_format': False, 'contains_device_calibration': False}
    write(output / 'bundle-report.json', json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
