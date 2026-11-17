#!/usr/bin/env python3
"""Fail publication on private keys, host identity files or supplied private needles."""
import argparse, base64, hashlib, io, json, re, tarfile, zipfile
from pathlib import Path, PurePosixPath
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('path',type=Path)
p.add_argument('--needles-json',type=Path,help='Private local JSON; never copy it into a public repository')
p.add_argument('--report',type=Path,required=True)
a=p.parse_args(); needles=[]
if a.needles_json:
    d=json.loads(a.needles_json.read_text())
    needles=[x.encode() for x in d.get('text',[])]+[bytes.fromhex(x) for x in d.get('raw_hex',[])]
findings=[];count=0
badname=re.compile(r'(^|/)(?:authorized_keys|dropbear_(?:rsa|ecdsa|ed25519)_host_key|id_(?:rsa|ecdsa|ed25519)|machine-id|config\.bin|cal-pci-[^/]+\.bin)$',re.I)
key=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')
def scan(name,data,depth=0):
    global count
    count+=1
    if depth>5 or len(data)>256*1024*1024:
        findings.append({'path':name,'reason':'inspection_limit'});return
    if badname.search(name):findings.append({'path':name,'reason':'device_identity_filename'})
    if key.search(data):findings.append({'path':name,'reason':'private_key'})
    if re.search(rb'(?i)[A-Z]:[\\/]Users[\\/][^\s"\x00]+',data):
        findings.append({'path':name,'reason':'personal_windows_path'})
    if any(v and v in data for v in needles):findings.append({'path':name,'reason':'private_needle'})
    # Device addresses in C byte templates are otherwise invisible to text grep.
    if name.endswith(('.c','.h','.patch')):
        for m in re.finditer(rb'(?:static const u8|^\+static const u8) [^\n]+\[\] = \{(.*?)\};',data,re.S|re.M):
            raw=bytes(int(x,16) for x in re.findall(rb'0x([a-fA-F0-9]{2})\b',m[1]))
            if any(v and v in raw for v in needles):findings.append({'path':name,'reason':'private_c_byte_template'})
    if data[:4] in (b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08'):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for x in z.infolist():
                    if x.file_size>128*1024*1024:raise ValueError('Archive member too large')
                    if not x.is_dir():scan(name+'!'+x.filename,z.read(x),depth+1)
        except Exception:findings.append({'path':name,'reason':'unreadable_zip'})
    elif name.endswith(('.tar','.tar.gz','.tgz','.tar.xz')):
        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                for x in t:
                    pp=PurePosixPath(x.name)
                    if pp.is_absolute() or '..' in pp.parts:raise ValueError('Unsafe archive path')
                    if x.isfile():
                        if x.size>128*1024*1024:raise ValueError('Archive member too large')
                        scan(name+'!'+x.name,t.extractfile(x).read(),depth+1)
        except Exception:findings.append({'path':name,'reason':'unreadable_tar'})
root=a.path.resolve()
if root.is_file():scan(root.name,root.read_bytes())
else:
    for f in sorted(root.rglob('*')):
        if f.is_file() and '.git' not in f.relative_to(root).parts:
            scan(f.relative_to(root).as_posix(),f.read_bytes())
r={'passed':not findings,'objects_scanned':count,'findings':findings,'private_values_in_report':False}
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r));raise SystemExit(0 if r['passed'] else 1)
