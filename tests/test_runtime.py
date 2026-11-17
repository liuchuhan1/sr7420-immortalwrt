#!/usr/bin/env python3
"""Format/integrity checks using synthetic data; never accesses router hardware."""
import hashlib,os,struct,subprocess,tempfile
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
def tlv(tag,b):return struct.pack('<II',tag,len(b))+b+b'\0'*(-len(b)%4)
with tempfile.TemporaryDirectory(prefix='sr7420-runtime-') as tmp:
 t=Path(tmp)
 for source,name in [('sha256-file.c','sha256'),('stock-import.c','stock-import')]:
  subprocess.run(['cc','-std=gnu11','-O2',str(repo/'installer/src'/source),'-o',str(t/name)],check=True)
 for n in [0,1,55,56,63,64,65,119,120,127,128,129,1048576]:
  p=t/'input';p.write_bytes(os.urandom(n));actual=subprocess.check_output([str(t/'sha256'),str(p)],text=True).split()[0]
  assert actual==hashlib.sha256(p.read_bytes()).hexdigest(),n
 stock=t/'stock';stock.mkdir();out=t/'out';data={}
 for i,name in enumerate(['amss.bin','m3.bin','bdwlan.b01','bdwlan.b02','caldata_0.bin','caldata_1.bin','fw_ini_cfg.bin','regdb.bin']):
  data[name]=bytes([i+1])*(257+i);(stock/name).write_bytes(data[name])
 strings=b'local-mac-address\0';s=struct.pack('>I',1)+b'\0'*4+struct.pack('>III',3,6,0)+bytes.fromhex('027420000001')+b'\0'*2+struct.pack('>II',2,9)
 dtb=struct.pack('>10I',0xd00dfeed,56+len(s)+len(strings),56,56+len(s),40,17,16,0,len(strings),len(s))+b'\0'*16+s+strings
 d=t/'board.dtb';d.write_bytes(dtb);m=t/'mac';m.write_text('02:00:00:00:00:22\n')
 subprocess.run([str(t/'stock-import'),str(stock),str(out),str(d),str(m)],check=True,stdout=subprocess.DEVNULL)
 assert (out/'firmware-2.bin').read_bytes()==b'QCOM-ATH12K-FW\0\0'+tlv(1,b'\x03')+tlv(2,data['amss.bin'])+tlv(3,data['m3.bin'])
 expected=b'QCA-ATH12K-BOARD\0'+b'\0'*3
 for band,name in [('2g','bdwlan.b01'),('5g','bdwlan.b02')]:
  key=('bus=pci,qmi-chip-id=0,qmi-board-id=255,variant=zte-sr7420-'+band).encode();expected+=tlv(0,tlv(0,key)+tlv(1,data[name]))
 assert (out/'board-2.bin').read_bytes()==expected
 assert (out/'cal-pci-0001:01:00.0.bin').read_bytes()==data['caldata_0.bin']
 assert (out/'cal-pci-0000:01:00.0.bin').read_bytes()==data['caldata_1.bin']
 assert d.read_bytes()[76:82]==bytes.fromhex('020000000022')
 # A corrupt DTB must be rejected rather than patched blindly.
 d.write_bytes(b'not a device tree')
 assert subprocess.run([str(t/'stock-import'),str(stock),str(out),str(d),str(m)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
for f in [repo/'installer/sr7420-usb.sh.in',repo/'installer/init-usb.sh',* (repo/'files').rglob('*')]:
 if f.is_file() and f.read_bytes().startswith(b'#!/'):subprocess.run(['sh','-n',str(f)],check=True)
print('SHA-256 boundary vectors, firmware/BDF TLVs, full per-radio calibration, DTB MAC patch and shell syntax passed')
