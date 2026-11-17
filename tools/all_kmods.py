#!/usr/bin/env python3
"""Select all target-visible kmod packages and report the solved result."""
import argparse, json, re, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=['select','report'])
p.add_argument('--topdir', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args(); s=a.topdir.resolve()
assert (s/'include/toplevel.mk').is_file(), 'Not an ImmortalWrt tree'
metadata=s/'tmp/.config-package.in'
assert metadata.is_file(), 'Run make defconfig once to generate package metadata'
requested=sorted(set(re.findall(r'^\s*config PACKAGE_(kmod-[A-Za-z0-9_+.-]+)\s*$',metadata.read_text(),re.M)))
assert len(requested)>100, 'Incomplete kmod metadata; refusing to call this all-kmods'
config=(s/'.config').read_text()
if a.action=='select':
    # y installs a module package into the image; it does not mean kernel builtin.
    keep=set(re.findall(r'^CONFIG_PACKAGE_(kmod-[^=]+)=y$',config,re.M))
    values={'ALL_KMODS':'y',**{'PACKAGE_'+n:('y' if n in keep else 'm') for n in requested}}
    for k,v in values.items():
        key='CONFIG_'+k; pat=r'^(?:'+re.escape(key)+r'=.*|# '+re.escape(key)+r' is not set)$'
        line=key+'='+v
        config=re.sub(pat,lambda _:line,config,flags=re.M) if re.search(pat,config,re.M) else config+'\n'+line+'\n'
    (s/'.config').write_text(config)
    subprocess.run(['make','defconfig'],cwd=s,check=True)
    config=(s/'.config').read_text()
selected={n:m for n,m in re.findall(r'^CONFIG_PACKAGE_(kmod-[^=]+)=([ym])$',config,re.M)}
missing=[n for n in requested if n not in selected]
report={'requested_count':len(requested),'selected_count':len(selected),'selected':selected,
        'unselected_after_dependency_resolution':missing,
        'unselected_meaning':'Unavailable dependencies, architecture restrictions or mutually exclusive choices; not a successful build',
        'compiled':False}
if a.action=='report':
    dirs=list((s/'build_dir').glob('target-*/linux-*/linux-*'))
    dirs=[x for x in dirs if (x/'.config').is_file()]
    assert len(dirs)==1, 'Provide an isolated single-kernel build tree'
    k=dirs[0]; cfg=(k/'.config').read_text()
    report['kernel_modular_symbols']=sorted(re.findall(r'^CONFIG_([^=]+)=m$',cfg,re.M))
    report['kernel_builtin_symbols']=sorted(re.findall(r'^CONFIG_([^=]+)=y$',cfg,re.M))
    report['modules_built']=len(list(k.rglob('*.ko')))
    report['modules_builtin']=(k/'modules.builtin').read_text().splitlines()
    apks=sorted((s/'bin').rglob('kmod-*.apk'))
    report['apk_files']=[str(x.relative_to(s/'bin')) for x in apks]
    report['compiled']=bool(apks) and report['modules_built']>0
    assert report['compiled'], 'No built modules/APKs'
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['requested_count','selected_count','compiled']}))
