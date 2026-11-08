#!/usr/bin/env python3
"""Test SD automount, Unicode names and clean SD-only controller reprobe."""
import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

DEV = '/dev/mmcblk1p1'
UUID = '6802-7F21'
CID = '03534441434c4345805941242a01129b'
ROOT = Path('/mnt/sdcard')
HOST = Path('/sys/bus/platform/devices/f9820000.mmc')
DRIVER = Path('/sys/bus/platform/drivers/dw_mmc')

def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT,
                                   timeout=60).strip()

def identity():
    assert Path('/sys/class/block/mmcblk1/device/cid').read_text().strip() == CID
    assert run('blkid', '-s', 'UUID', '-o', 'value', DEV) == UUID

def errors():
    return {str(i): Path('/sys/kernel/debug/mmc'+str(i)+'/err_stats').read_text()
            for i in (0, 1)}

identity()
assert HOST.joinpath('driver').resolve() == DRIVER
assert subprocess.run(['findmnt', '-rn', '-S', DEV],
                      stdout=subprocess.DEVNULL).returncode == 1
result = {'kernel': os.uname().release, 'uuid': UUID, 'cid': CID,
          'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'errors_before': errors(), 'fsck_before': run('fsck.exfat', '-n', DEV)}
ROOT.stat()
list(ROOT.iterdir())  # Trigger the generated automount.
result['initial_mount'] = run('findmnt', '-rn', '-S', DEV, '-o', 'SOURCE,TARGET,FSTYPE,OPTIONS')
assert str(ROOT) in result['initial_mount'] and 'exfat' in result['initial_mount']
directory = ROOT / ('ec6108-测试-'+secrets.token_hex(4))
directory.mkdir()
file = directory / '中文长文件名-写入校验.bin'
renamed = directory / '中文长文件名-重命名后校验.bin'
payload = os.urandom(2*1048576)
expected = hashlib.sha256(payload).hexdigest()
unbound = False
try:
    with file.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fdatasync(stream.fileno())
    file.rename(renamed)
    os.sync()
    run('systemctl', 'stop', 'mnt-sdcard.automount', 'mnt-sdcard.mount')
    assert subprocess.run(['findmnt', '-rn', '-S', DEV],
                          stdout=subprocess.DEVNULL).returncode == 1
    DRIVER.joinpath('unbind').write_text(HOST.name)
    unbound = True
    run('udevadm', 'settle', '--timeout=15')
    assert not Path('/sys/class/block/mmcblk1').exists()
    DRIVER.joinpath('bind').write_text(HOST.name)
    unbound = False
    run('udevadm', 'settle', '--timeout=15')
    for _ in range(100):
        if Path(DEV).exists():
            break
        time.sleep(.1)
    identity()
    run('systemctl', 'start', 'mnt-sdcard.automount')
    assert hashlib.sha256(renamed.read_bytes()).hexdigest() == expected
    result.update(unicode_create_rename_readback=True,
                  clean_sd_controller_reprobe=True,
                  automount_after_reprobe=True, bytes=len(payload), sha256=expected)
finally:
    if unbound:
        DRIVER.joinpath('bind').write_text(HOST.name)
        run('udevadm', 'settle', '--timeout=15')
    identity()
    run('systemctl', 'start', 'mnt-sdcard.automount')
    for own_file in (file, renamed):
        if own_file.exists():
            own_file.unlink()
    directory.rmdir()
    os.sync()

run('systemctl', 'stop', 'mnt-sdcard.automount', 'mnt-sdcard.mount')
result['fsck_after'] = run('fsck.exfat', '-n', DEV)
run('systemctl', 'start', 'mnt-sdcard.automount')
list(ROOT.iterdir())
result['final_mount'] = run('findmnt', '-rn', '-S', DEV, '-o', 'SOURCE,TARGET,FSTYPE,OPTIONS')
result['errors_after'] = errors()
result['temporary_files_removed'] = True
print(json.dumps(result, indent=2, ensure_ascii=False))
