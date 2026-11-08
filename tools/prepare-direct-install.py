#!/usr/bin/env python3
"""Validate hardware and stage the RAM installer; explicitly replaces the old OS."""
import argparse
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import zlib

ENV_SIZE = 65536
ROOT_OFFSET = 34*1024*1024
KERNEL_OFFSET = 14*1024*1024
ENV_OFFSET = 1024*1024
ENV_PARTITION_SIZE = 1024*1024
NEW_LAYOUT = 'mmcblk0:14M(boot),20M(kernel),-(armbian-root)'
OLD_LAYOUT = 'mmcblk0:1M(boot),1M(bootargs),4M(baseparam),4M(pqparam),4M(logo),20M(kernel),64M(busybox),512M(backup),-(ubuntu)'

def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=60).strip()

def hardware(manifest):
    compatible = Path('/proc/device-tree/compatible').read_bytes()
    assert b'hi3798mv100' in compatible, 'Expected Hi3798MV100'
    sys = Path('/sys/class/block/mmcblk0')
    assert (sys/'device/type').read_text().strip() == 'MMC', 'Expected internal eMMC'
    assert int((sys/'size').read_text())*512 == manifest['emmc_bytes'], 'Unexpected eMMC capacity'
    direct = (Path('/sys/class/block/mmcblk0p1/size').read_text().strip() == '28672')
    starts = [0,28672,69632] if direct else [0,2048,4096,12288,20480,28672]
    sizes = [28672,40960,(manifest['emmc_bytes']-ROOT_OFFSET)//512] if direct else [2048,2048,8192,8192,8192,40960]
    for i,(start,size) in enumerate(zip(starts,sizes),1):
        part = Path('/sys/class/block/mmcblk0p'+str(i))
        assert int((part/'start').read_text()) == start, 'Unexpected partition offset'
        assert int((part/'size').read_text()) == size, 'Unexpected partition size'
    return (sys/'device/cid').read_text().strip()

def decode(raw):
    assert zlib.crc32(raw[4:ENV_SIZE]) == struct.unpack('<I',raw[:4])[0], 'Invalid environment CRC'
    return OrderedDict(x.split(b'=',1) for x in raw[4:ENV_SIZE].split(b'\0\0',1)[0].split(b'\0'))

def environment(raw, root, temporary=False):
    entries = decode(raw)
    for key in list(entries):
        if key.startswith((b'ec6108_',b'armbian_')):
            del entries[key]
    layout = NEW_LAYOUT if root == '/dev/mmcblk0p3' else OLD_LAYOUT
    if temporary:
        layout = 'mmcblk0:14M,20M,-' if root == '/dev/mmcblk0p3' else 'mmcblk0:1M,1M,4M,4M,4M,20M,64M,512M,-'
    arguments = ('console=ttyAMA0,115200 root='+root+' rootfstype=ext4 rootwait ro '
                 'blkdevparts='+layout+' mem=1G mmz=ddr,0,0,48M vmalloc=500M')
    if temporary:
        arguments += ' init=/sbin/ec6108-ram-maintenance'
    assert len('setenv bootargs '+arguments) < 256, 'Bootloader command expansion exceeds its limit'
    for key in entries:
        if key.startswith(b'bootargs_'):
            entries[key] = arguments.encode()
    entries[b'bootargs'] = arguments.encode()
    entries[b'armbian_args'] = arguments.encode()
    entries[b'armbian_select'] = b'setenv bootargs ${armbian_args}'
    entries[b'armbian_read'] = b'mmc read 0 0x1FFFFC0 0x7000 0x4000'
    entries[b'armbian_boot'] = b'bootm 0x1FFFFC0'
    entries[b'bootcmd'] = b'run armbian_select armbian_read armbian_boot'
    payload = b'\0'.join(k+b'='+v for k,v in entries.items())+b'\0\0'
    assert len(payload) <= ENV_SIZE-4
    payload = payload.ljust(ENV_SIZE-4,b'\xff')
    return struct.pack('<I',zlib.crc32(payload))+payload+raw[ENV_SIZE:]

def write_all(stream, data):
    remaining = memoryview(data)
    while remaining:
        n = stream.write(remaining)
        assert n and n > 0, 'Short device write'
        remaining = remaining[n:]

def write_environment(prepared):
    path = Path('/dev/mmcblk0')
    before = read_environment()
    assert len(prepared) == len(before)
    decode(prepared)
    with path.open('r+b',buffering=0) as stream:
        stream.seek(ENV_OFFSET)
        try:
            write_all(stream,prepared[:ENV_SIZE]);os.fsync(stream.fileno())
            stream.seek(ENV_OFFSET);assert stream.read(len(prepared)) == prepared
        except BaseException:
            stream.seek(ENV_OFFSET);write_all(stream,before[:ENV_SIZE]);os.fsync(stream.fileno());raise

def read_environment():
    with open('/dev/mmcblk0','rb') as stream:
        stream.seek(ENV_OFFSET)
        return stream.read(ENV_PARTITION_SIZE)

def validate_image(image, manifest):
    assert len(image) == manifest['kernel_bytes']
    assert hashlib.sha256(image).hexdigest() == manifest['kernel_sha256']
    header = image[:64]
    fields = struct.unpack('>7I4B32s',header)
    assert fields[0] == 0x27051956 and fields[3]+64 == len(image)
    assert zlib.crc32(header[:4]+bytes(4)+header[8:]) == fields[1]
    assert zlib.crc32(image[64:]) == fields[6]

def write_kernel(image, manifest):
    validate_image(image,manifest)
    data = image+bytes(20*1024*1024-len(image))
    with open('/dev/mmcblk0','r+b',buffering=0) as stream:
        stream.seek(KERNEL_OFFSET)
        write_all(stream,data);os.fsync(stream.fileno())
        stream.seek(KERNEL_OFFSET);assert stream.read(len(data)) == data, 'Kernel readback differs'

def stage(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory/'manifest.json').read_text())
    cid = hardware(manifest)
    run('sha256sum','-c',str(directory/'SHA256SUMS'))
    # SHA256SUMS uses filenames relative to the staging directory.
    assert (directory/'rootfs.tar.gz').is_file()
    root = run('findmnt','-n','-o','SOURCE','/')
    if root == '/dev/mmcblk0p3':
        raise RuntimeError('RAM entry from the direct three-partition root is not validated; use the USB installer')
    if root.startswith('/dev/loop'):
        assert str(directory).startswith('/.hinas/var/lib/ec6108-install')
        boot_root = '/.hinas'
        root_device = '/dev/mmcblk0p9'
    elif root in ('/dev/mmcblk0p3','/dev/mmcblk0p9'):
        boot_root = ''
        root_device = root
    else:
        raise RuntimeError('Unsupported current root: '+root)
    destination = Path(boot_root+'/sbin/ec6108-ram-maintenance')
    destination.write_bytes((directory/'ram-init.sh').read_bytes());destination.chmod(0o755)
    image = (directory/'uImage').read_bytes();validate_image(image,manifest)
    current = read_environment()
    prepared = environment(current,root_device,temporary=True)
    (directory/'boot-before.bin').write_bytes(current)
    (directory/'target.json').write_text(json.dumps({'emmc_cid':cid,'root_before':root,'root_device':root_device})+'\n')
    write_kernel(image,manifest)
    write_environment(prepared)
    os.sync()
    print(json.dumps({'stage':'ready-for-ram-boot','emmc_cid':cid,'root_before':root}),flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args = parser.parse_args()
    os.chdir(args.directory)
    stage(args.directory)
