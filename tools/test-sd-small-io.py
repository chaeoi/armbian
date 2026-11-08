#!/usr/bin/env python3
"""Verify small SD writes with an explicit durable flush after every update."""
import argparse,hashlib,json,os,secrets,statistics,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--operations',type=int,default=128);p.add_argument('--record',type=Path,required=True);p.add_argument('--keep',action='store_true');a=p.parse_args()
if not 1<=a.operations<=1024:p.error('Operations must be 1..1024')
def cmd(argv):
 r=subprocess.run(argv,check=True,capture_output=True,text=True,timeout=60);return r.stdout.strip()
DEV='/dev/mmcblk1p1'
if subprocess.run(['findmnt','-rn','-S',DEV],capture_output=True).returncode==0:raise SystemExit('SD already mounted')
fs=cmd(['blkid','-s','TYPE','-o','value',DEV]);uuid=cmd(['blkid','-s','UUID','-o','value',DEV])
if fs not in ('exfat','vfat'):raise SystemExit('Expected existing FAT/exFAT')
root=Path(tempfile.mkdtemp(prefix='ec6108-sdsmall-',dir='/run'));file=root/('EC8'+secrets.token_hex(2).upper()+'.TMP');mounted=False;created=False;retained=False
try:
 cmd(['mount','-t',fs,'-o','rw,noatime,nosuid,nodev,noexec',DEV,str(root)]);mounted=True
 expected=bytearray(1048576);latencies=[]
 with file.open('xb') as stream:
  created=True;stream.write(expected);stream.flush();os.fdatasync(stream.fileno())
 with file.open('r+b',buffering=0) as stream:
  for i in range(a.operations):
   offset=secrets.randbelow(256)*4096;data=os.urandom(4096);started=time.monotonic()
   if os.pwrite(stream.fileno(),data,offset)!=len(data):raise RuntimeError('Short small write')
   os.fdatasync(stream.fileno());latencies.append((time.monotonic()-started)*1000)
   expected[offset:offset+4096]=data
 cmd(['umount',str(root)]);mounted=False;cmd(['blockdev','--flushbufs',DEV]);cmd(['mount','-t',fs,'-o','ro,noatime,nosuid,nodev,noexec',DEV,str(root)]);mounted=True
 wanted=hashlib.sha256(expected).hexdigest();actual=hashlib.sha256(file.read_bytes()).hexdigest()
 if actual!=wanted:raise RuntimeError('Cold readback differs after small writes')
 ordered=sorted(latencies)
 result={'kernel':os.uname().release,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cid':Path('/sys/class/block/mmcblk1/device/cid').read_text().strip(),'uuid':uuid,'filesystem':fs,'filename':file.name,'bytes':len(expected),'sha256':wanted,'operations':a.operations,'write_bytes_per_operation':4096,'fdatasync_after_each_write':True,'median_ms':round(statistics.median(latencies),3),'p95_ms':round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],3),'maximum_ms':round(max(latencies),3),'latencies_ms':[round(x,3) for x in latencies],'unmount_cache_flush_readback_passed':True}
 a.record.write_text(json.dumps(result,indent=2)+'\n');retained=a.keep
 print(json.dumps(result,indent=2),flush=True)
finally:
 if mounted:
  if created and not retained and file.exists():cmd(['mount','-o','remount,rw',str(root)]);file.unlink()
  cmd(['umount',str(root)])
 root.rmdir()
