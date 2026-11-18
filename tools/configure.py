#!/usr/bin/env python3
"""Overlay the SR7420 port onto the pinned, otherwise clean ImmortalWrt tree."""
import argparse,json,os,shutil,subprocess,tarfile,io
from pathlib import Path
from luci_radio_labels import patch_file, patch_header_file
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--topdir',type=Path,required=True)
p.add_argument('--backup',type=Path,required=True)
p.add_argument('--skip-revision-check',action='store_true')
a=p.parse_args();root=Path(__file__).resolve().parents[1];s=a.topdir.resolve();backup=a.backup.resolve()
assert (s/'include/toplevel.mk').is_file()
assert not backup.exists(),'Use a new backup directory'
assert not backup.is_relative_to(s),'Backups must be outside the build root'
up=json.loads((root/'upstream.json').read_text())
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=s,text=True).strip()
assert a.skip_revision_check or head==up['commit'],'Wrong upstream revision'
backup.mkdir(parents=True,mode=0o700)
for name in ['.config','files','bin/targets/zte/zx279133','private-key.pem','public-key.pem']:
 f=s/name
 if not f.exists():continue
 d=backup/name;d.parent.mkdir(parents=True,exist_ok=True)
 if f.is_dir():shutil.move(str(f),d)
 else:shutil.copy2(f,d)
for n in json.loads((root/'config/remove-inherited.json').read_text()):
 f=s/n;assert f.resolve().is_relative_to(s)
 if f.is_dir():shutil.rmtree(f)
 elif f.exists():f.unlink()
shutil.copytree(root/'overlay',s,dirs_exist_ok=True)
patch_file(s/'feeds/luci/modules/luci-base/htdocs/luci-static/resources/network.js')
patch_header_file(s/'feeds/luci/modules/luci-base/ucode/template/header.ut')
shutil.copytree(root/'files',s/'files',symlinks=True)
for f in (s/'files').rglob('*'):
 if f.is_file() and (f.read_bytes().startswith(b'#!/') or '/etc/init.d/' in f.as_posix()):f.chmod(0o755)
(s/'files/etc/shadow').chmod(0o600)
rc=s/'files/etc/rc.d';rc.mkdir(parents=True,exist_ok=True)
os.symlink('../init.d/sr7420-radio',rc/'S18sr7420-radio')
shutil.copy2(root/'config/release.config',s/'.config')
# Generate a project-only APK key. Never add the private half to Git.
subprocess.run(['openssl','ecparam','-name','prime256v1','-genkey','-noout','-out',str(s/'private-key.pem')],check=True)
(s/'private-key.pem').chmod(0o600)
subprocess.run(['openssl','ec','-in',str(s/'private-key.pem'),'-pubout','-out',str(s/'public-key.pem')],check=True,stderr=subprocess.DEVNULL)
subprocess.run(['make','defconfig'],cwd=s,check=True)
subprocess.run(['python3',str(root/'tools/all_kmods.py'),'select','--topdir',str(s),'--output',str(root/'build/kmod-selection.json')],check=True)
print(json.dumps({'configured':True,'upstream':head,'router_storage_written':False}))
