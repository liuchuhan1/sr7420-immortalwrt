#!/usr/bin/env python3
"""Select all target-visible kmod packages and report the solved result."""
import argparse, json, re, subprocess
from pathlib import Path
from apk_metadata import collect_kmods
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=['select','report'])
p.add_argument('--topdir', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args(); s=a.topdir.resolve()
assert (s/'include/toplevel.mk').is_file(), 'Not an ImmortalWrt tree'
if a.action=='select':
    # Refresh package definitions before discovering new or changed kmods.
    subprocess.run(['make','defconfig'],cwd=s,check=True)
metadata=s/'tmp/.config-package.in'
assert metadata.is_file(), 'Run make defconfig once to generate package metadata'
requested=sorted(set(re.findall(r'^\s*(?:menuconfig|config) PACKAGE_(kmod-[A-Za-z0-9_+.-]+)\s*$',metadata.read_text(),re.M)))
assert len(requested)>100, 'Incomplete kmod metadata; refusing to call this all-kmods'
unavailable=json.loads((Path(__file__).resolve().parents[1]/'config/kmod-unavailable.json').read_text())['packages']
config=(s/'.config').read_text()
if a.action=='select':
    # y installs a module package into the image; it does not mean kernel builtin.
    keep=set(re.findall(r'^CONFIG_PACKAGE_(kmod-[^=]+)=y$',config,re.M))
    values={'ALL_KMODS':'y',**{'PACKAGE_'+n:('n' if n in unavailable else 'y' if n in keep else 'm') for n in requested}}
    for k,v in values.items():
        key='CONFIG_'+k; pat=r'^(?:'+re.escape(key)+r'=.*|# '+re.escape(key)+r' is not set)$'
        line=key+'='+v
        config=re.sub(pat,lambda _:line,config,flags=re.M) if re.search(pat,config,re.M) else config+'\n'+line+'\n'
    (s/'.config').write_text(config)
    subprocess.run(['make','defconfig'],cwd=s,check=True)
    config=(s/'.config').read_text()
selected={n:m for n,m in re.findall(r'^CONFIG_PACKAGE_(kmod-[^=]+)=([ym])$',config,re.M)}
missing=[n for n in requested if n not in selected]
blocks={m.group(1):m.group(2) for m in re.finditer(r'^\s*(?:menuconfig|config) PACKAGE_(kmod-[A-Za-z0-9_+.-]+)\s*\n(.*?)(?=^\s*(?:config |menuconfig |endmenu)|\Z)',metadata.read_text(),re.M|re.S)}
details=[]
for n in missing:
    b=blocks.get(n,'')
    title=re.search(r'(?:tristate|bool)\s+"([^"\n]+)"',b)
    details.append({**unavailable.get(n,{}),'name':n,'title':title.group(1) if title else n,'dependency_expressions':re.findall(r'^\s*depends on (.+)$',b,re.M),'status':'unavailable_for_pinned_target' if n in unavailable else 'not_selected_by_kconfig'})
report={'requested_count' :len(requested),'selected_count':len(selected),'selected':selected,
        'unselected_after_dependency_resolution':missing,
        'unselected_meaning':'Unavailable dependencies, architecture restrictions or mutually exclusive choices; not a successful build',
        'compiled':False,'unselected_details':details}
if a.action=='report':
    dirs=list((s/'build_dir').glob('target-*/linux-*/linux-*'))
    dirs=[x for x in dirs if (x/'.config').is_file()]
    assert len(dirs)==1, 'Provide an isolated single-kernel build tree'
    k=dirs[0]; cfg=(k/'.config').read_text()
    preferences=json.loads((Path(__file__).resolve().parents[1]/'config/module-preferences.json').read_text())
    values=dict(re.findall(r'^CONFIG_([^=]+)=(.+)$',cfg,re.M))
    report['module_preferences']={**preferences,'solved':{name:values.get(name,'n') for name in preferences['preferred_module_symbols']}}
    report['kernel_modular_symbols']=sorted(re.findall(r'^CONFIG_([^=]+)=m$',cfg,re.M))
    report['kernel_builtin_symbols']=sorted(re.findall(r'^CONFIG_([^=]+)=y$',cfg,re.M))
    report['modules_built']=len(list(k.rglob('*.ko')))
    report['modules_builtin']=(k/'modules.builtin').read_text().splitlines()
    report.update(collect_kmods(s,k,selected))
    records=report['package_records']
    actual={item['name'] for item in records if item['name']!='kernel'}
    report['apk_files']=[item['file'] for item in records]
    report['packaged_count']=len(actual)
    report['selected_without_apk']=sorted(set(selected)-actual)
    report['compiled']=bool(records) and report['modules_built']>0 and not any(
        report[key] for key in ['selected_without_apk','invalid_apks','ambiguous_packages'])
    # Always write a failure report instead of concealing missing packages.
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['requested_count','selected_count','compiled']}))
if a.action=='report' and not report['compiled']:raise SystemExit(1)
