#!/usr/bin/env python3
"""Validate attached media with direct reads and temporary filesystem files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

MIB = 1024 * 1024
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sample-mib', type=int, default=4)
parser.add_argument('--file-mib', type=int, default=1)
parser.add_argument('--skip-sd-write', action='store_true', help='Read the SD card but do not retest its known failed writes')
args = parser.parse_args()
if not 1 <= args.sample_mib <= 64 or not 1 <= args.file_mib <= 64:
    parser.error('Sample and temporary file sizes must be between 1 and 64 MiB')

def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs)

def read_sample(device, offset, count):
    started = time.monotonic()
    data = command(['dd', 'if=' + device, 'bs=1M', 'skip=' + str(offset),
                    'count=' + str(count), 'iflag=direct', 'status=none'], timeout=90).stdout
    if len(data) != count * MIB:
        raise RuntimeError('Short device read: ' + device)
    return {'offset_MiB': offset, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
            'MiB_per_second': round(count / (time.monotonic() - started), 2)}

results = []
for name in ('sda', 'sdb', 'mmcblk1'):
    sysfs = Path('/sys/class/block') / name
    if not sysfs.exists():
        raise SystemExit('Required attached media is absent: ' + name)
    if name.startswith('sd') and 'usb' not in str((sysfs / 'device').resolve()):
        raise SystemExit('Refusing non-USB block device: ' + name)
    size = int((sysfs / 'size').read_text()) * 512
    offsets = [0, (size // MIB) // 2, size // MIB - args.sample_mib]
    result = {'device': '/dev/' + name, 'bytes': size,
              'path': str((sysfs / 'device').resolve()), 'direct_reads': []}
    for offset in offsets:
        first = read_sample(result['device'], offset, args.sample_mib)
        second = read_sample(result['device'], offset, args.sample_mib)
        if first['sha256'] != second['sha256']:
            raise RuntimeError('Repeated direct reads differ: ' + name)
        first['repeat_matches'] = True
        result['direct_reads'].append(first)
        print(json.dumps({'direct_read_passed': {'device': result['device'], **first}}), flush=True)
    print(json.dumps({'read_complete': result}), flush=True)
    results.append(result)

usb_filesystems = []
for device in ('/dev/sda', '/dev/sdb'):
    probe = subprocess.run(['blkid', '-s', 'TYPE', '-o', 'value', device], capture_output=True, text=True)
    if probe.stdout.strip() == 'vfat':
        usb_filesystems.append(device)
if not usb_filesystems:
    raise SystemExit('Expected existing USB FAT filesystem is absent')
# Linux USB disk letters depend on enumeration order; identify the filesystem.
write_devices = usb_filesystems + ([] if args.skip_sd_write else ['/dev/mmcblk1p1'])
for device in write_devices:
    probe = command(['blkid', '-s', 'TYPE', '-o', 'value', device], text=True).stdout.strip()
    if probe != 'vfat':
        raise SystemExit('Expected existing FAT filesystem: ' + device)
    if subprocess.run(['findmnt', '-rn', '-S', device], capture_output=True).returncode == 0:
        raise SystemExit('Refusing to test an already mounted filesystem: ' + device)
    mountpoint = Path(tempfile.mkdtemp(prefix='ec6108-media-', dir='/run'))
    testfile = None
    mounted = False
    try:
        command(['mount', '-t', 'vfat', '-o', 'rw,nosuid,nodev,noexec', device, str(mountpoint)])
        mounted = True
        free = os.statvfs(mountpoint)
        if free.f_bavail * free.f_frsize < 32 * MIB:
            raise RuntimeError('Insufficient space for temporary media test')
        fd, path = tempfile.mkstemp(prefix='EC6108-', suffix='.tmp', dir=mountpoint)
        testfile = Path(path)
        expected = hashlib.sha256()
        started = time.monotonic()
        with os.fdopen(fd, 'wb') as stream:
            for _ in range(args.file_mib):
                data = os.urandom(MIB)
                stream.write(data)
                expected.update(data)
            stream.flush()
            os.fsync(stream.fileno())
        relative = testfile.name
        command(['umount', str(mountpoint)])
        mounted = False
        command(['mount', '-t', 'vfat', '-o', 'ro,nosuid,nodev,noexec', device, str(mountpoint)])
        mounted = True
        observed = hashlib.sha256(testfile.read_bytes()).hexdigest()
        if observed != expected.hexdigest():
            raise RuntimeError('Temporary file readback differs: ' + device)
        command(['mount', '-o', 'remount,rw', str(mountpoint)])
        testfile.unlink()
        testfile = None
        os.sync()
        print(json.dumps({'file_write_read_delete': {'device': device, 'bytes': args.file_mib*MIB,
              'sha256': observed, 'unmount_remount_verified': True,
              'temporary_file_removed': True,
              'seconds': round(time.monotonic()-started, 2)}}), flush=True)
    finally:
        if mounted:
            if testfile is not None and testfile.exists():
                subprocess.run(['mount', '-o', 'remount,rw', str(mountpoint)], capture_output=True)
                testfile.unlink(missing_ok=True)
                os.sync()
            command(['umount', str(mountpoint)])
        mountpoint.rmdir()
print(json.dumps({'read_checks_and_usb_file_checks_passed': True,
                  'sd_write_tested': not args.skip_sd_write,
                  'all_requested_storage_checks_passed': not args.skip_sd_write,
                  'unformatted_usb': 'empty MBR partition table; raw reads verified; not formatted'}), flush=True)
