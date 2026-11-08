#!/usr/bin/env python3
"""Verify an SD file survives unmount and block-cache invalidation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bytes', type=int, default=512, dest='byte_count')
parser.add_argument('--keep-record', type=Path, help='Keep the verified file for a reboot test; save its identity here')
args = parser.parse_args()
if not 512 <= args.byte_count <= 64 * 1024 * 1024:
    parser.error('Test file size must be between 512 bytes and 64 MiB')
DEVICE = '/dev/mmcblk1p1'
NAME = 'EC8' + secrets.token_hex(2).upper() + '.TMP'
root = Path(tempfile.mkdtemp(prefix='ec6108-sd-', dir='/run'))
sample = os.urandom(args.byte_count)
filesystem = subprocess.check_output(['blkid', '-s', 'TYPE', '-o', 'value', DEVICE], text=True).strip()
if filesystem not in ('vfat', 'exfat'):
    root.rmdir()
    raise SystemExit('Expected an existing FAT or exFAT filesystem')
cid = Path('/sys/block/mmcblk1/device/cid').read_text().strip()
result = {'device': DEVICE, 'bytes': len(sample),
          'cid': cid, 'filesystem': filesystem, 'filename': NAME,
          'bus': Path('/sys/kernel/debug/mmc1/ios').read_text(),
          'expected_sha256': hashlib.sha256(sample).hexdigest()}
mounted = False
file = root / NAME
retained = False
created = False

def command(*args):
    return subprocess.run(args, check=True, capture_output=True, timeout=40)

try:
    if subprocess.run(['findmnt', '-rn', '-S', DEVICE], capture_output=True).returncode == 0:
        raise RuntimeError('SD filesystem already mounted')
    if subprocess.check_output(['blockdev', '--getro', DEVICE], text=True).strip() != '0':
        raise RuntimeError('SD card is read-only')
    command('mount', '-t', filesystem, '-o', 'rw,nosuid,nodev,noexec', DEVICE, str(root))
    mounted = True
    free = os.statvfs(root)
    if free.f_bavail * free.f_frsize < len(sample) + 8 * 1024 * 1024:
        raise RuntimeError('Insufficient space for the temporary test file')
    started = time.monotonic()
    with file.open('xb') as stream:
        created = True
        stream.write(sample)
        stream.flush()
        os.fsync(stream.fileno())
    result['write_and_fsync_seconds'] = round(time.monotonic() - started, 3)
    result['cached_read_matches'] = file.read_bytes() == sample
    command('umount', str(root))
    mounted = False
    command('blockdev', '--flushbufs', DEVICE)
    command('mount', '-t', filesystem, '-o', 'ro,nosuid,nodev,noexec', DEVICE, str(root))
    mounted = True
    result['file_exists_after_remount'] = file.exists()
    result['persisted'] = file.exists() and hashlib.sha256(file.read_bytes()).hexdigest() == result['expected_sha256']
    if result['persisted'] and args.keep_record:
        args.keep_record.parent.mkdir(parents=True, exist_ok=True)
        args.keep_record.write_text(json.dumps(result, indent=2) + '\n')
        retained = True
        result['retained_for_reboot'] = True
    elif file.exists():
        command('mount', '-o', 'remount,rw', str(root))
        file.unlink()
        os.sync()
    print(json.dumps(result, indent=2), flush=True)
finally:
    if mounted:
        if created and not retained and file.exists():
            command('mount', '-o', 'remount,rw', str(root))
            file.unlink()
            os.sync()
        command('umount', str(root))
    root.rmdir()
if not result.get('persisted'):
    raise SystemExit(2)
