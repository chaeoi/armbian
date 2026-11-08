#!/usr/bin/env python3
"""Read and compare USB storage samples without mounting or modifying them."""
import hashlib
import json
import os
from pathlib import Path
import time

for name in ('sda', 'sdb'):
    device = Path('/dev')/name
    sysfs = Path('/sys/class/block')/name
    if not sysfs.exists() or 'usb' not in str((sysfs/'device').resolve()):
        raise SystemExit('Expected USB device is absent: '+name)
    result = {'device':str(device),'usb_path':str((sysfs/'device').resolve()),
              'bytes':int((sysfs/'size').read_text())*512,'passes':[]}
    descriptor = os.open(device, os.O_RDONLY)
    try:
        header = os.pread(descriptor,512,0)
        result['sector0_all_zero'] = not any(header)
        result['sector0_boot_signature'] = header[-2:]==b'\x55\xaa'
        for repeat in range(2):
            os.posix_fadvise(descriptor,0,64*1024*1024,os.POSIX_FADV_DONTNEED)
            start=time.monotonic();total=0;checksum=hashlib.sha256()
            while total < 64*1024*1024:
                block=os.pread(descriptor,1024*1024,total)
                if not block:raise RuntimeError('Unexpected end of USB device')
                checksum.update(block);total+=len(block)
            elapsed=time.monotonic()-start
            result['passes'].append({'read_bytes':total,'seconds':round(elapsed,3),
                'MiB_per_second':round(total/1048576/elapsed,2),'sha256':checksum.hexdigest()})
        result['repeated_read_matches'] = result['passes'][0]['sha256']==result['passes'][1]['sha256']
        if not result['repeated_read_matches']:raise RuntimeError('USB read results differ')
        print(json.dumps(result,indent=2),flush=True)
    finally:
        os.close(descriptor)
