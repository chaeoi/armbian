#!/usr/bin/env python3
"""Check a consistent metadata snapshot, never fsck the mounted root itself."""
import errno, fcntl, json, os
from pathlib import Path
import re, select, shutil, stat, subprocess, tempfile, time
root_source=subprocess.check_output(['findmnt','-n','-o','SOURCE','/'],text=True).strip()
if not root_source.startswith('/dev/loop'):
    raise SystemExit('Expected the separate Armbian loop root')
if subprocess.check_output(['findmnt','-n','-o','FSTYPE','/run'],text=True).strip()!='tmpfs':
    raise SystemExit('Snapshot must be on a separate RAM filesystem')
# e2fsprogs probes root writability by creating /.ismount-test-file.
# Use a RAM chroot without mount tables so that this probe cannot deadlock
# against the freeze. The input remains the exact frozen block device.
scratch=Path(tempfile.mkdtemp(prefix='ec6108-rootmeta-',dir='/run'))
binary=Path(shutil.which('e2image')).resolve()
libs=subprocess.check_output(['ldd',str(binary)],text=True)
paths={str(binary)} | set(re.findall(r'(?:=>\s+|^\s*)(/[^\s]+)',libs,re.M))
for path in paths:
    destination=scratch/path.lstrip('/')
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,destination);destination.chmod(0o755)
(scratch/'dev').mkdir()
os.mknod(scratch/'dev/source',stat.S_IFBLK|0o600,os.stat(root_source).st_rdev)
# /run is nodev; inherit the usable device mount through a bind mount.
subprocess.run(['mount','--bind',root_source,str(scratch/'dev/source')],check=True)
with (scratch/'dev/source').open('rb') as source:
    source.seek(1080)
    if source.read(2)!=b'\x53\xef':raise RuntimeError('Invalid ext4 superblock magic')
name=str(scratch/'snapshot.img')
environment=os.environ.copy();environment['EXT2FS_NO_MTAB_OK']='1';environment['LC_ALL']='C'
root_fd=os.open('/',os.O_RDONLY)
read_fd,write_fd=os.pipe()
started=time.monotonic()
pid=os.fork()
if pid==0:
    os.close(write_fd)
    ready,_,_=select.select([read_fd],[],[],90)
    if not ready or os.read(read_fd,4)!=b'done':
        try:fcntl.ioctl(root_fd,0xC0045878,0)
        finally:os._exit(99)
    os._exit(0)
os.close(read_fd)
frozen=False
try:
    try:
        fcntl.ioctl(root_fd,0xC0045877,0);frozen=True
        copied=subprocess.run(['chroot',str(scratch),str(binary),'-r','/dev/source','/snapshot.img'],env=environment,capture_output=True,text=True,timeout=60)
        if copied.returncode:raise RuntimeError(copied.stdout+copied.stderr)
    finally:
        try:
            if frozen:fcntl.ioctl(root_fd,0xC0045878,0)
        except OSError as error:
            if error.errno!=errno.EINVAL:raise
        finally:
            try:os.write(write_fd,b'done')
            except BrokenPipeError:pass
            os.close(write_fd)
        _,status=os.waitpid(pid,0)
        if os.waitstatus_to_exitcode(status)!=0:
            raise RuntimeError('Emergency thaw guard triggered; snapshot discarded')
    result=subprocess.run(['e2fsck','-fn',name],capture_output=True,text=True,timeout=120)
    output={'root':root_source,'snapshot_consistency':'filesystem frozen while copying metadata; separate tmpfs output; emergency thaw guard armed',
            'snapshot_allocated_bytes':Path(name).stat().st_blocks*512,'snapshot_and_check_seconds':round(time.monotonic()-started,3),
            'fsck_exit_code':result.returncode,'fsck_output':result.stdout+result.stderr,'passed':result.returncode==0}
    print(json.dumps(output,indent=2),flush=True)
    if result.returncode:raise SystemExit(result.returncode)
finally:
    os.close(root_fd)
    subprocess.run(['umount',str(scratch/'dev/source')],check=True)
    shutil.rmtree(scratch)
