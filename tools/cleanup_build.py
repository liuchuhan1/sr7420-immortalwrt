#!/usr/bin/env python3
"""Inspect derived build files; archive and prune only explicit approved candidates."""
import argparse,hashlib,json,shutil,subprocess,tarfile,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--buildroot',required=True,type=Path)
p.add_argument('--archive-dir',required=True,type=Path)
p.add_argument('--apply',action='store_true')
a=p.parse_args();s=a.buildroot.resolve();assert (s/'Makefile').is_file() and (s/'include/toplevel.mk').is_file()
# Never prune source trees, downloads, build_dir, staging_dir, signing keys or research.
candidates=[s/x for x in ['tmp','logs'] if (s/x).is_dir()]
for q in candidates:assert q.resolve().is_relative_to(s) and not q.is_symlink()
rows=[]
for q in candidates:
    n=sum(f.stat().st_size for f in q.rglob('*') if f.is_file() and not f.is_symlink())
    rows.append({'path':q.name,'bytes':n})
if a.apply and rows:
    # Refuse concurrent compilers; no kill command or broad make clean is used.
    processes=subprocess.run(['ps','-eo','comm='],capture_output=True,text=True,check=True).stdout.splitlines()
    assert not any(x.strip() in ['make','cc1','cc1plus','ld','ld.lld'] for x in processes), 'Build still active'
    arc=a.archive_dir.resolve();assert not arc.is_relative_to(s/'tmp') and not arc.is_relative_to(s/'logs')
    arc.mkdir(parents=True,exist_ok=True);target=arc/('derived-'+str(int(time.time()))+'.tar.gz')
    with tarfile.open(target,'x:gz') as t:
        for q in candidates:t.add(q,arcname=q.name)
    with tarfile.open(target) as t:
        for m in t:
            if m.isfile():
                f=t.extractfile(m)
                while f.read(1024*1024):pass
    target.with_suffix(target.suffix+'.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n')
    for q in candidates:
        assert q.parent==s and q.name in ['tmp','logs'] and not q.is_symlink();shutil.rmtree(q)
print(json.dumps({'apply':a.apply,'candidates':rows,'free_bytes_after':shutil.disk_usage(s).free},indent=2))
