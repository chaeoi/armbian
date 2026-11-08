#!/usr/bin/env python3
"""Install this private EC6108V9 release over SSH through a temporary RAM system."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
defaults = json.loads((HERE/'connection.json').read_text()) if (HERE/'connection.json').exists() else {}
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--host',default=defaults.get('host'))
p.add_argument('--identity',default=defaults.get('identity'))
p.add_argument('--known-hosts',default=defaults.get('known_hosts'))
p.add_argument('--host-key-alias',default=defaults.get('host_key_alias'))
p.add_argument('--flash',action='store_true',help='Replace the internal OS and merge the root partitions')
p.add_argument('--stage-only',action='store_true',help='Transfer and verify files without changing boot or OS data')
a = p.parse_args()
if not all((a.host,a.identity,a.known_hosts)):
    p.error('--host, --identity and --known-hosts are required')
identity=Path(a.identity).expanduser()
known_hosts=Path(a.known_hosts).expanduser()
if not identity.is_absolute():identity=HERE/identity
if not known_hosts.is_absolute():known_hosts=HERE/known_hosts
ssh = ['ssh','-i',str(identity),'-o','IdentitiesOnly=yes',
       '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ControlMaster=no',
       '-o','UserKnownHostsFile='+str(known_hosts),
       '-o','ConnectTimeout=5','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
if a.host_key_alias:ssh+=['-o','HostKeyAlias='+a.host_key_alias]
ssh.append(a.host)
def remote(*args,timeout=60,source=None,check=True):
    r = subprocess.run(ssh+[shlex.join(args)],stdin=source,capture_output=True,timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(r.stdout.decode(errors='replace')+r.stderr.decode(errors='replace'))
    return r
def wait_for(command, timeout):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            r=remote('sh','-c',command,timeout=10,check=False)
            if r.returncode==0:return r.stdout.decode().strip()
        except (subprocess.TimeoutExpired,RuntimeError):pass
        time.sleep(2)
    raise TimeoutError('Device did not reach expected state: '+command)
def upload(local, destination):
    with local.open('rb') as stream:
        r = subprocess.run(ssh+['umask 077; cat > '+shlex.quote(destination)],stdin=stream,
                           capture_output=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))

manifest=json.loads((HERE/'manifest.json').read_text())
files=[]
for line in (HERE/'SHA256SUMS').read_text().splitlines():
    expected,name=line.split('  ',1)
    assert '/' not in name and name not in ('.','..')
    file=HERE/name
    assert hashlib.sha256(file.read_bytes()).hexdigest()==expected,'Local checksum mismatch: '+name
    files.append(file)
print('Verified local release checksums.',flush=True)
info=remote('sh','-c',"uname -r; cat /sys/class/block/mmcblk0/device/type; cat /sys/class/block/mmcblk0/size; cat /proc/device-tree/compatible | tr '\\000' '\\n'; findmnt -n -o SOURCE /").stdout.decode()
print(info,flush=True)
assert 'hi3798mv100' in info and '\nMMC\n' in info
assert str(manifest['emmc_bytes']//512) in info,'Unexpected eMMC size'
hardware_code = ('scope={"__name__":"hardware_preflight"}\n'
                 'exec('+repr((HERE/'prepare-install.py').read_text())+',scope)\n'
                 'print(scope["hardware"]('+repr(manifest)+'))\n')
print('Verified hardware and partition geometry: '+remote('python3','-c',hardware_code).stdout.decode().strip(),flush=True)
if not a.flash and not a.stage_only:
    print('Preflight only. Run flash.sh to replace the internal OS.',flush=True)
    sys.exit(0)

ram=remote('test','-e','/etc/ec6108-ram-mode',check=False).returncode==0
if not ram:
    root=remote('findmnt','-n','-o','SOURCE','/').stdout.decode().strip()
    assert root.startswith('/dev/loop') or root in ('/dev/mmcblk0p3','/dev/mmcblk0p9')
    stage=('/.hinas' if root.startswith('/dev/loop') else '')+'/var/lib/ec6108-install'
    remote('mkdir','-p',stage)
    for file in files+[HERE/'SHA256SUMS']:
        if file.stat().st_size>1024*1024:
            existing=remote('sha256sum',stage+'/'+file.name,check=False,timeout=45)
            if existing.returncode==0 and existing.stdout.decode().split()[0]==hashlib.sha256(file.read_bytes()).hexdigest():
                print('Already verified '+file.name,flush=True)
                continue
        print('Uploading '+file.name,flush=True);upload(file,stage+'/'+file.name)
    if a.stage_only:
        r=remote('sh','-c','cd '+shlex.quote(stage)+' && sha256sum -c SHA256SUMS',timeout=90)
        print(r.stdout.decode(),flush=True)
        print('Staged and verified files; boot and OS areas have not been modified.',flush=True)
        sys.exit(0)
    print('Preparing the temporary RAM boot.',flush=True)
    r=remote('python3',stage+'/prepare-install.py',stage,timeout=120)
    print(r.stdout.decode(),flush=True)
    remote('systemctl','reboot','--no-block',check=False)
    print('Waiting for Armbian in RAM.',flush=True)
    wait_for("test -f /etc/ec6108-ram-mode && test \"$(findmnt -n -o FSTYPE /)\" = tmpfs && systemctl is-active --quiet ssh.service",600)

ram_manifest=json.loads(remote('cat','/opt/ec6108-install/manifest.json').stdout)
assert ram_manifest==manifest,'RAM release differs'
active = remote('systemctl','is-active','--quiet','ec6108-flash.service',check=False).returncode==0
existing = remote('cat','/run/ec6108-flash-status.json',check=False)
ready = existing.returncode==0 and json.loads(existing.stdout).get('phase')=='ready-to-reboot'
if not active and not ready:
    remote('sh','-c','rm -f /run/ec6108-flash-status.json; systemd-run --unit=ec6108-flash --collect /usr/bin/python3 /opt/ec6108-install/install-in-ram.py')
deadline=time.monotonic()+600;last=None
while time.monotonic()<deadline:
    r=remote('cat','/run/ec6108-flash-status.json',check=False)
    if r.returncode==0:
        status=json.loads(r.stdout)
        if status['phase']!=last:
            print(json.dumps(status),flush=True);last=status['phase']
        if last=='failed':raise RuntimeError(status)
        if last=='ready-to-reboot':break
    time.sleep(2)
else:raise TimeoutError('RAM installation timed out')
remote('systemctl','reboot','--no-block',check=False)
print('Waiting for the single Armbian system on eMMC.',flush=True)
wait_for("test ! -e /etc/ec6108-ram-mode && test \"$(findmnt -n -o SOURCE /)\" = /dev/mmcblk0p3 && systemctl is-active --quiet ec6108-system-check.service",180)
r=remote('/usr/local/sbin/ec6108-verify-system')
print(r.stdout.decode(),flush=True)
print('Installation complete. Internal eMMC contains one Armbian OS, with no vendor fallback.',flush=True)
