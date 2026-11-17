#!/usr/bin/env python3
"""Compile small source-available helpers with the matching musl toolchain."""
import argparse,subprocess,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--topdir',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1];s=a.topdir.resolve()
t=next((s/'staging_dir').glob('toolchain-aarch64_cortex-a53_gcc-14.3.0_musl'))
e=os.environ.copy();e['STAGING_DIR']=str(s/'staging_dir/target-aarch64_cortex-a53_musl')
out=r/'build/runtime';out.mkdir(parents=True,exist_ok=True)
for src,name in [('sha256-file.c','sha256'),('pci-quiesce.c','pci-quiesce'),('quiesce-check.c','quiesce-check'),('stock-import.c','stock-import')]:
 subprocess.run([str(t/'bin/aarch64-openwrt-linux-musl-gcc'),'-Os','-static','-Wall','-Wextra',str(r/'installer/src'/src),'-o',str(out/name)],env=e,check=True)
f=s/'files/usr/sbin/quiesce-check';f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes((out/'quiesce-check').read_bytes());f.chmod(0o755)
