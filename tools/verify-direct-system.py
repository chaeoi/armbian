#!/usr/bin/env python3
"""Read-only checks for the finalized, single-OS EC6108V9 installation."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

cfg = json.loads(Path('/etc/ec6108-system.json').read_text())
def run(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()
assert os.uname().release == cfg['kernel_release'], 'Unexpected running kernel'
assert os.stat('/').st_dev == os.stat('/dev/mmcblk0p3').st_rdev, 'Expected direct eMMC root'
assert run('blkid', '-s', 'UUID', '-o', 'value', '/dev/mmcblk0p3') == cfg['root_uuid'], 'Root UUID changed'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == cfg['emmc_cid'], 'eMMC identity changed'
assert int(Path('/sys/class/block/mmcblk0p3/start').read_text()) * 512 == cfg['root_offset'], 'Root position changed'
assert not Path('/sys/class/block/mmcblk0p4').exists(), 'Unexpected old partitions'
with open('/dev/mmcblk0p2', 'rb') as stream:
    assert hashlib.sha256(stream.read(cfg['kernel_bytes'])).hexdigest() == cfg['kernel_sha256'], 'Kernel changed'
    assert not any(stream.read()), 'Unexpected second kernel in kernel partition'
with open('/dev/mmcblk0', 'rb') as stream:
    stream.seek(1024*1024)
    assert hashlib.sha256(stream.read(1024*1024)).hexdigest() == cfg['environment_sha256'], 'Boot environment changed'
subprocess.run(['systemctl', 'is-active', '--quiet', 'ssh.service'], check=True)
print('Verified: direct Armbian root, fixed kernel, permanent boot environment and SSH.')
