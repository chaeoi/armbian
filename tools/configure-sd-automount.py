#!/usr/bin/env python3
"""Configure the verified SD filesystem at /mnt/sdcard without formatting it."""
import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--uuid', required=True)
p.add_argument('--activate', action='store_true')
a = p.parse_args()
if not re.fullmatch(r'[A-Fa-f0-9]+-[A-Fa-f0-9]+', a.uuid):
    p.error('Expected a FAT/exFAT UUID')
if os.geteuid() != 0:
    raise SystemExit('Run as root')

device = Path('/dev/disk/by-uuid') / a.uuid
actual = subprocess.check_output(
    ['blkid', '-s', 'TYPE', '-o', 'value', str(device)], text=True).strip()
if actual != 'exfat':
    raise SystemExit('Expected the verified exFAT card')
target = Path('/mnt/sdcard')
fstab = Path('/etc/fstab')
text = fstab.read_text()
line = ('UUID=' + a.uuid + ' /mnt/sdcard exfat '
        'defaults,noatime,nosuid,nodev,nofail,x-systemd.automount,'
        'x-systemd.device-timeout=5s,x-systemd.mount-timeout=30s 0 0')
for existing in text.splitlines():
    fields = existing.split()
    if not fields or fields[0].startswith('#'):
        continue
    if fields[1] == str(target) or fields[0] == 'UUID=' + a.uuid:
        if existing != line:
            raise SystemExit('Conflicting fstab entry; no changes made')

if line not in text.splitlines():
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise SystemExit('Mount directory is not empty; no changes made')
    backup = Path('/var/lib/ec6108-backups/fstab-before-sd-automount')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(fstab, backup)
    target.mkdir(mode=0o755, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.fstab-sd-', dir='/etc')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text.rstrip() + '\n' + line + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, fstab)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

subprocess.run(['systemctl', 'daemon-reload'], check=True)
if a.activate:
    subprocess.run(['systemctl', 'start', 'mnt-sdcard.automount'], check=True)
print(json.dumps({'uuid': a.uuid, 'mountpoint': str(target),
                  'fstab_entry': line, 'automount_started': a.activate}))
