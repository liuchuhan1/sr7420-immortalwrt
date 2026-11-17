#!/usr/bin/env python3
"""Fail publication on private keys, host identity files or supplied private needles."""
import argparse, base64, gzip, hashlib, io, json, os, re, stat, subprocess, tarfile, tempfile, zipfile
from pathlib import Path, PurePosixPath
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('path',type=Path)
p.add_argument('--needles-json',type=Path,help='Private local JSON; never copy it into a public repository')
p.add_argument('--report',type=Path,required=True)
p.add_argument('--apk-tool',type=Path,help='Trusted host apk executable required to inspect APK payloads')
p.add_argument('--reviewed-matches-json',type=Path,help='Private, manually reviewed upstream matches bound to exact artifact and needle SHA256')
a=p.parse_args(); needles=[]
if a.needles_json:
    d=json.loads(a.needles_json.read_text())
    needles=[x.encode() for x in d.get('text',[])]+[bytes.fromhex(x) for x in d.get('raw_hex',[])]
reviewed={};reviewed_matches=[];reviewed_public_matches=[]
if a.reviewed_matches_json:
    for item in json.loads(a.reviewed_matches_json.read_text())['entries']:
        artifact,needle=item['artifact_sha256'],item['needle_sha256']
        assert re.fullmatch('[0-9a-f]{64}',artifact) and re.fullmatch('[0-9a-f]{64}',needle)
        assert item.get('reason')
        upstream=item.get('upstream_verified') is True
        public_url=item.get('public_repository_url_verified') is True
        assert upstream != public_url, 'Exactly one manual review category required'
        key=(artifact,needle);assert key not in reviewed
        reviewed[key]=(item['reason'], 'upstream' if upstream else 'public_repository_url')
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
    matches=[v for v in needles if v and v in data]
    if matches:
        digest=hashlib.sha256(data).hexdigest();uncleared=False
        for value in matches:
            review=reviewed.get((digest,hashlib.sha256(value).hexdigest()))
            if review:
                reason,category=review
                target=reviewed_matches if category=='upstream' else reviewed_public_matches
                target.append({'path':name,'artifact_sha256':digest,'reason':reason})
            else:uncleared=True
        if uncleared:findings.append({'path':name,'reason':'private_needle'})
    # Device addresses in C byte templates are otherwise invisible to text grep.
    if name.endswith(('.c','.h','.patch')):
        for m in re.finditer(rb'(?:static const u8|^\+static const u8) [^\n]+\[\] = \{(.*?)\};',data,re.S|re.M):
            raw=bytes(int(x,16) for x in re.findall(rb'0x([a-fA-F0-9]{2})\b',m[1]))
            if any(v and v in raw for v in needles):findings.append({'path':name,'reason':'private_c_byte_template'})
    if name.endswith('.adb'):
        if not a.apk_tool or not a.apk_tool.is_file():
            findings.append({'path':name,'reason':'adb_metadata_not_inspected'});return
        try:
            with tempfile.TemporaryDirectory(prefix='sr7420-adb-scan-') as tmp:
                index=Path(tmp)/'index.adb';index.write_bytes(data)
                metadata=subprocess.run([str(a.apk_tool.resolve()),'adbdump',str(index)],
                    capture_output=True,check=True,timeout=60).stdout
                scan(name+'!ADB-METADATA.txt',metadata,depth+1)
        except Exception:findings.append({'path':name,'reason':'unreadable_adb'})
    elif name.endswith('.apk'):
        if not a.apk_tool or not a.apk_tool.is_file():
            findings.append({'path':name,'reason':'apk_payload_not_inspected'});return
        try:
            with tempfile.TemporaryDirectory(prefix='sr7420-apk-scan-') as tmp:
                package=Path(tmp)/'input.apk';package.write_bytes(data)
                metadata=subprocess.run([str(a.apk_tool.resolve()),'adbdump',str(package)],
                    capture_output=True,check=True,timeout=60).stdout
                scan(name+'!APK-METADATA.txt',metadata,depth+1)
                destination=Path(tmp)/'payload';destination.mkdir()
                subprocess.run([str(a.apk_tool.resolve()),'--allow-untrusted','extract',
                    '--no-chown','--destination',str(destination),str(package)],
                    capture_output=True,check=True,timeout=60)
                for file in sorted(destination.rglob('*')):
                    member=name+'!'+file.relative_to(destination).as_posix()
                    if file.is_symlink():scan(member,os.readlink(file).encode(),depth+1)
                    elif file.is_file():scan(member,file.read_bytes(),depth+1)
        except Exception:findings.append({'path':name,'reason':'unreadable_apk'})
    elif data[:6]==b'070701':
        try:
            offset=0
            while True:
                assert data[offset:offset+6]==b'070701'
                fields=[int(data[offset+6+i*8:offset+14+i*8],16) for i in range(13)]
                mode,size,namesize=fields[1],fields[6],fields[11]
                assert 0<namesize<=4096 and size<=128*1024*1024
                rawname=data[offset+110:offset+110+namesize];assert rawname[-1:]==b'\0'
                filename=rawname[:-1].decode();path=PurePosixPath(filename)
                assert not path.is_absolute() and '..' not in path.parts
                offset=(offset+110+namesize+3)&~3
                if filename=='TRAILER!!!':break
                assert offset+size<=len(data)
                if stat.S_ISREG(mode) or stat.S_ISLNK(mode):scan(name+'!'+filename,data[offset:offset+size],depth+1)
                offset=(offset+size+3)&~3
        except Exception:findings.append({'path':name,'reason':'unreadable_cpio'})
    elif data[:2]==b'\x1f\x8b' and not name.endswith(('.tar.gz','.tgz')):
        try:scan(name+'!gzip',gzip.decompress(data),depth+1)
        except Exception:findings.append({'path':name,'reason':'unreadable_gzip'})
    elif data[:4] in (b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08'):
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
                    elif x.issym() or x.islnk():scan(name+'!'+x.name,x.linkname.encode(),depth+1)
        except Exception:findings.append({'path':name,'reason':'unreadable_tar'})
root=a.path.resolve()
if root.is_file():scan(root.name,root.read_bytes())
else:
    for f in sorted(root.rglob('*')):
        if '.git' in f.relative_to(root).parts:continue
        if f.is_symlink():scan(f.relative_to(root).as_posix(),os.readlink(f).encode())
        elif f.is_file():scan(f.relative_to(root).as_posix(),f.read_bytes())
r={'passed':not findings,'objects_scanned':count,'findings':findings,'reviewed_upstream_matches':reviewed_matches,'reviewed_public_repository_matches':reviewed_public_matches,'private_values_in_report':False}
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r));raise SystemExit(0 if r['passed'] else 1)
