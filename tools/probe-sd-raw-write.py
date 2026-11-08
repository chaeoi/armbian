#!/usr/bin/env python3
"""DESTRUCTIVE: test five SD sector ranges with direct I/O, bypassing the filesystem.

Requires an explicitly authorized expendable card. This damages existing files;
formatting is a separate step. The CID and exact device size must match.
"""
import argparse
import hashlib
import json
import mmap
import os
import subprocess
import time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--cid', required=True)
p.add_argument('--size', required=True, type=int)
p.add_argument('--record', required=True, type=Path)
a = p.parse_args()
device = '/dev/mmcblk1'
sys = Path('/sys/class/block/mmcblk1')
driver = Path('/sys/bus/platform/drivers/dw_mmc')

def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT,
                                   timeout=45).strip()

def identity():
    assert (sys / 'device/cid').read_text().strip() == a.cid, 'CID differs'
    assert int((sys / 'size').read_text()) * 512 == a.size, 'Size differs'
    assert (sys / 'removable').read_text().strip() == '1', 'Not removable SD'
    assert (driver / 'f9820000.mmc').exists(), 'Expected the SD host'
    assert run('blockdev', '--getro', device) == '0', 'SD is read-only'
    for dev in [device] + ['/dev/'+x.name for x in sys.glob('mmcblk1p*')]:
        assert subprocess.run(['findmnt', '-rn', '-S', dev],
                              stdout=subprocess.DEVNULL).returncode == 1, 'Mounted: '+dev

def direct_read(offset):
    fd = os.open(device, os.O_RDONLY | os.O_DIRECT)
    try:
        with mmap.mmap(-1, 4096) as buffer:
            n = os.preadv(fd, [buffer], offset)
            assert n == 4096, 'Short direct read'
            return buffer[:]
    finally:
        os.close(fd)

identity()
assert 16*1048576 <= a.size <= 128*1024**3
offsets = sorted({1048576, (a.size//4)//4096*4096,
                  (a.size//2)//4096*4096, (a.size*3//4)//4096*4096,
                  (a.size-1048576)//4096*4096})
result = {'kernel': os.uname().release, 'cid': a.cid, 'device_bytes': a.size,
          'device': device, 'method': 'O_DIRECT reads and O_DIRECT|O_DSYNC writes',
          'test_ranges': [], 'filesystem_bypassed': True}
def save():
    a.record.write_text(json.dumps(result, indent=2)+'\n')

for offset in offsets:
    identity()
    before = direct_read(offset)
    payload = os.urandom(4096)
    started = time.monotonic()
    fd = os.open(device, os.O_RDWR | os.O_DIRECT | os.O_DSYNC)
    try:
        with mmap.mmap(-1, 4096) as buffer:
            buffer[:] = payload
            n = os.pwritev(fd, [buffer], offset)
            assert n == 4096, 'Short direct write'
            os.fsync(fd)
    finally:
        os.close(fd)
    write_seconds = time.monotonic()-started
    run('blockdev', '--flushbufs', device)
    after = direct_read(offset)
    entry = {'offset': offset, 'bytes': 4096,
             'before_sha256': hashlib.sha256(before).hexdigest(),
             'expected_sha256': hashlib.sha256(payload).hexdigest(),
             'after_sha256': hashlib.sha256(after).hexdigest(),
             'direct_readback_matches': after == payload,
             'readback_is_old_data': after == before,
             'write_and_sync_seconds': round(write_seconds, 6)}
    result['test_ranges'].append(entry)
    save()
    print(json.dumps(entry), flush=True)

result['all_passed'] = all(x['direct_readback_matches'] for x in result['test_ranges'])
save()
print(json.dumps({'all_passed': result['all_passed'], 'record': str(a.record)}), flush=True)
raise SystemExit(0 if result['all_passed'] else 2)
