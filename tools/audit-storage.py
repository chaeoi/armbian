#!/usr/bin/env python3
"""Check actual attached media, preserving temporary files across one reboot."""
import argparse, hashlib, json, os
from pathlib import Path
import secrets, subprocess, tempfile, time
MIB=1048576
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('phase', choices=('prepare','verify'))
p.add_argument('--record',default='/var/lib/ec6108-storage-audit.json')
a=p.parse_args();record=Path(a.record)
def cmd(argv,**kw):
    return subprocess.run(argv,check=True,capture_output=True,timeout=90,**kw)
def sha_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
        for data in iter(lambda:f.read(MIB),b''):h.update(data)
    return h.hexdigest()
def save(state):
    with record.open('w') as f:
        json.dump(state,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def mounted(device):
    return subprocess.run(['findmnt','-rn','-S',device],capture_output=True).returncode==0
state={'kernel':os.uname().release,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'media':[]}
if a.phase=='verify':
    state=json.loads(record.read_text())
    if state['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        raise SystemExit('Reboot has not occurred')
    for item in state['media']:
        root=Path(tempfile.mkdtemp(prefix='ec6108-audit-',dir='/run')) if item['device'] else Path('/var/tmp')
        try:
            if item['device']:
                if mounted(item['device']):raise RuntimeError('Media already mounted')
                uuid=cmd(['blkid','-s','UUID','-o','value',item['device']],text=True).stdout.strip()
                if uuid!=item['uuid']:raise RuntimeError('Media identity changed')
                cmd(['mount','-t',item['filesystem'],'-o','ro,nosuid,nodev,noexec',item['device'],str(root)])
            file=root/item['filename']
            if file.stat().st_size!=item['bytes'] or sha_file(file)!=item['sha256']:
                raise RuntimeError('Persisted data mismatch: '+str(file))
            item['reboot_verified']=True
            if item['device']:cmd(['mount','-o','remount,rw',str(root)])
            file.unlink();os.sync();item['temporary_file_removed']=True
            print(json.dumps(item),flush=True)
        finally:
            if item['device']:
                if mounted(item['device']):cmd(['umount',str(root)])
                root.rmdir()
    state['verified_kernel']=os.uname().release
    state['verified_boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    state['passed']=True;save(state);raise SystemExit()
if record.exists():raise SystemExit('Refusing to overwrite an existing record')
# Discover disks, since enumeration letters and attached disk count can change.
media=[(None,None,32)]
for sys in sorted(Path('/sys/class/block').iterdir()):
    if (sys/'partition').exists():continue
    if 'usb' not in str((sys/'device').resolve()) and sys.name!='mmcblk1':continue
    device='/dev/'+sys.name
    size=int((sys/'size').read_text())*512
    reads=[]
    for off in (0,(size//MIB)//2,size//MIB-4):
        samples=[]
        for repeat in range(2):
            t=time.monotonic()
            data=cmd(['dd','if='+device,'bs=1M','skip='+str(off),'count=4','iflag=direct','status=none']).stdout
            if len(data)!=4*MIB:raise RuntimeError('Short direct read')
            samples.append(hashlib.sha256(data).hexdigest())
        if samples[0]!=samples[1]:raise RuntimeError('Repeated direct reads differ')
        reads.append({'offset_MiB':off,'bytes':4*MIB,'sha256':samples[0],'repeat_matches':True})
    print(json.dumps({'device':device,'direct_reads':reads}),flush=True)
    for dev in [device]+[str(x) for x in sorted(Path('/dev').glob(sys.name+'*')) if x.name!=sys.name]:
        fs=subprocess.run(['blkid','-s','TYPE','-o','value',dev],capture_output=True,text=True).stdout.strip()
        if fs in ('vfat','exfat'):
            media.append((dev,fs,4 if sys.name=='mmcblk1' else 8));break
    else:print(json.dumps({'device':device,'write_skipped':'No existing FAT/exFAT filesystem; disk preserved'}),flush=True)
for device,fs,count in media:
    root=Path(tempfile.mkdtemp(prefix='ec6108-audit-',dir='/run')) if device else Path('/var/tmp')
    file=root/('EC8'+secrets.token_hex(3).upper()+'.TMP')
    created=False
    try:
        if device:
            if mounted(device):raise RuntimeError('Media already mounted: '+device)
            cmd(['mount','-t',fs,'-o','rw,nosuid,nodev,noexec',device,str(root)])
        v=os.statvfs(root)
        if v.f_bavail*v.f_frsize<(count+16)*MIB:raise RuntimeError('Insufficient free space')
        h=hashlib.sha256();t=time.monotonic()
        with file.open('xb') as f:
            created=True
            for _ in range(count):
                data=os.urandom(MIB);h.update(data);f.write(data)
            f.flush();os.fsync(f.fileno())
        elapsed=time.monotonic()-t
        if device:
            cmd(['umount',str(root)]);cmd(['blockdev','--flushbufs',device])
            cmd(['mount','-t',fs,'-o','ro,nosuid,nodev,noexec',device,str(root)])
        if sha_file(file)!=h.hexdigest():raise RuntimeError('Readback failed')
        item={'device':device,'filesystem':fs or 'ext4-loop-on-emmc','filename':file.name,'bytes':count*MIB,'sha256':h.hexdigest(),'write_fsync_seconds':round(elapsed,3),'cache_invalidated_readback':True}
        if device:item['uuid']=cmd(['blkid','-s','UUID','-o','value',device],text=True).stdout.strip()
        state['media'].append(item);save(state)
        print(json.dumps(item),flush=True)
    except BaseException:
        if created and file.exists():
            if device:cmd(['mount','-o','remount,rw',str(root)])
            file.unlink();os.sync()
        raise
    finally:
        if device:
            if mounted(device):cmd(['umount',str(root)])
            root.rmdir()
print('Temporary files retained for reboot verification.',flush=True)
