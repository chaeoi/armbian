#!/usr/bin/env python3
"""Measure SD write/flush latency and verify each result after unmounting."""
import argparse,hashlib,json,os,secrets,signal,subprocess,tempfile,threading,time
from pathlib import Path
P=argparse.ArgumentParser(description=__doc__)
P.add_argument('phase',choices=('bench','verify'))
P.add_argument('--label',default='sd')
P.add_argument('--mib',type=int,default=16)
P.add_argument('--rounds',type=int,default=3)
P.add_argument('--record',type=Path)
P.add_argument('--keep',action='store_true')
a=P.parse_args()
if not 1<=a.mib<=128 or not 1<=a.rounds<=12:P.error('Limit 1..128 MiB and 1..12 rounds')
if (a.keep or a.phase=='verify') and not a.record:P.error('--record required')
DEV='/dev/mmcblk1p1';SYS=Path('/sys/class/block/mmcblk1');DBG=Path('/sys/kernel/debug/mmc1')
def cmd(argv):
    r=subprocess.run(argv,capture_output=True,text=True,timeout=60)
    if r.returncode:raise RuntimeError(str(argv)+': '+r.stdout+r.stderr)
    return r.stdout.strip()
def read(p):
    try:return Path(p).read_text().strip()
    except OSError:return ''
def diskstat():return list(map(int,(SYS/'stat').read_text().split()))
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def delta(before,after):
    return {name:after[i]-before[i] for name,i in [('reads',0),('read_sectors',2),('read_ms',3),('writes',4),('write_sectors',6),('write_ms',7),('io_busy_ms',9),('io_weighted_ms',10)]}
if subprocess.run(['findmnt','-rn','-S',DEV],capture_output=True).returncode==0:raise SystemExit('SD already mounted')
fs=cmd(['blkid','-s','TYPE','-o','value',DEV]);uuid=cmd(['blkid','-s','UUID','-o','value',DEV]);cid=read(SYS/'device/cid')
if fs not in ('exfat','vfat'):raise SystemExit('Only existing exFAT/FAT supported')
root=Path(tempfile.mkdtemp(prefix='ec6108-sdbench-',dir='/run'));mounted=False;created=False;retained=False;file=None
stop=threading.Event();samples=[];stage=['idle'];worker=None
def monitor():
    while not stop.wait(.2):
        samples.append({'t':round(time.monotonic()-epoch,3),'stage':stage[0],'stats':diskstat(),'state':read(DBG/'state'),'request':read(DBG/'req')})
def mount(mode):
    global mounted
    cmd(['mount','-t',fs,'-o',mode+',noatime,nosuid,nodev,noexec',DEV,str(root)]);mounted=True
def unmount():
    global mounted
    cmd(['umount',str(root)]);mounted=False
signal.signal(signal.SIGTERM,lambda signum,frame:(_ for _ in ()).throw(SystemExit(128+signum)))
try:
    if a.phase=='verify':
        record=json.loads(a.record.read_text())
        if record['cid']!=cid or record['uuid']!=uuid:raise RuntimeError('Card identity changed')
        if record['boot_id']==read('/proc/sys/kernel/random/boot_id'):raise RuntimeError('No reboot since benchmark')
        file=root/record['filename'];mount('ro')
        actual=sha(file)
        if actual!=record['sha256'] or file.stat().st_size!=record['bytes']:raise RuntimeError('Reboot checksum mismatch')
        cmd(['mount','-o','remount,rw',str(root)]);file.unlink()
        record.update(reboot_verified=True,verified_kernel=os.uname().release,verified_boot_id=read('/proc/sys/kernel/random/boot_id'),temporary_file_removed=True)
        a.record.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
    else:
        mount('rw')
        v=os.statvfs(root)
        if v.f_bavail*v.f_frsize<(a.mib+32)*1048576:raise RuntimeError('Insufficient free space')
        file=root/('EC8'+secrets.token_hex(2).upper()+'.TMP')
        result={'label':a.label,'kernel':os.uname().release,'boot_id':read('/proc/sys/kernel/random/boot_id'),'device':DEV,'filesystem':fs,'cid':cid,'uuid':uuid,'filename':file.name,'bytes':a.mib*1048576,'bus':read(DBG/'ios'),'rounds':[]}
        epoch=time.monotonic();worker=threading.Thread(target=monitor,daemon=True);worker.start()
        for iteration in range(a.rounds):
            payload=os.urandom(a.mib*1048576);expected=hashlib.sha256(payload).hexdigest()
            before=diskstat();stage[0]='create' if iteration==0 else 'overwrite';started=time.monotonic()
            flags=os.O_RDWR|(os.O_CREAT|os.O_EXCL if iteration==0 else 0)
            fd=os.open(file,flags,0o600)
            if iteration==0:created=True
            chunks=[]
            try:
                for off in range(0,len(payload),1048576):
                    t=time.monotonic();data=memoryview(payload)[off:off+1048576]
                    while data:
                        n=os.write(fd,data)
                        if n<=0:raise RuntimeError('Short write')
                        data=data[n:]
                    chunks.append(round(time.monotonic()-t,6))
                written=time.monotonic();stage[0]='fdatasync';os.fdatasync(fd);synced=time.monotonic()
                os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
            finally:os.close(fd)
            after=diskstat();stage[0]='unmount';t=time.monotonic();unmount();umount_seconds=time.monotonic()-t
            cmd(['blockdev','--flushbufs',DEV]);mount('ro');stage[0]='verify';t=time.monotonic();actual=sha(file);read_seconds=time.monotonic()-t
            if actual!=expected:raise RuntimeError('Persisted checksum differs')
            entry={'iteration':iteration,'operation':'create' if iteration==0 else 'overwrite','write_seconds':round(written-started,3),'fdatasync_seconds':round(synced-written,3),'write_and_sync_seconds':round(synced-started,3),'MiB_per_second':round(a.mib/(synced-started),3),'unmount_seconds':round(umount_seconds,3),'read_seconds':round(read_seconds,3),'write_chunk_seconds':chunks,'diskstat_delta':delta(before,after),'sha256':expected,'unmount_cache_flush_readback_passed':True}
            result['rounds'].append(entry);result['sha256']=expected
            print(json.dumps({'round':entry,'label':a.label}),flush=True)
            if iteration+1<a.rounds:cmd(['mount','-o','remount,rw',str(root)])
        stage[0]='complete';stop.set();worker.join();result['samples']=samples;result['error_counters']=read(DBG/'err_stats')
        if a.record:a.record.write_text(json.dumps(result,indent=2)+'\n')
        if a.keep:retained=True
        else:cmd(['mount','-o','remount,rw',str(root)]);file.unlink();created=False
        print(json.dumps({'complete':True,'retained':retained,'record':str(a.record),'rounds':len(result['rounds']),'bus':result['bus']}),flush=True)
finally:
    stop.set()
    if worker:worker.join(timeout=2)
    if mounted:
        if created and not retained and file and file.exists():
            cmd(['mount','-o','remount,rw',str(root)]);file.unlink()
        unmount()
    root.rmdir()
