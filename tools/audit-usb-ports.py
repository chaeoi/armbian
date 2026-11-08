#!/usr/bin/env python3
"""Read USB hub port status without resetting or powering any port."""
import ctypes,fcntl,json,os,re
from pathlib import Path
class Control(ctypes.Structure):
    _fields_=[('request_type',ctypes.c_uint8),('request',ctypes.c_uint8),
              ('value',ctypes.c_uint16),('index',ctypes.c_uint16),
              ('length',ctypes.c_uint16),('timeout',ctypes.c_uint32),('data',ctypes.c_void_p)]
result={'root_hubs':[],'storage':[]}
for hub in sorted(Path('/sys/bus/usb/devices').iterdir()):
    if not re.fullmatch(r'usb\d+',hub.name):continue
    bus=int((hub/'busnum').read_text());number=int((hub/'devnum').read_text())
    item={'name':hub.name,'path':str(hub.resolve()),'ports':[]}
    fd=os.open('/dev/bus/usb/{:03d}/{:03d}'.format(bus,number),os.O_RDWR)
    try:
        for port in range(1,int((hub/'maxchild').read_text())+1):
            data=ctypes.create_string_buffer(4)
            request=Control(0xa3,0,0,port,4,1000,ctypes.addressof(data))
            fcntl.ioctl(fd,(3<<30)|(ctypes.sizeof(Control)<<16)|(ord('U')<<8),bytearray(bytes(request)),True)
            status=int.from_bytes(data.raw[:2],'little')
            item['ports'].append({'port':port,'status_hex':hex(status),'connection_detected':bool(status&1),'enabled':bool(status&2)})
    finally:os.close(fd)
    result['root_hubs'].append(item)
for disk in sorted(Path('/sys/class/block').glob('sd*')):
    if (disk/'partition').exists() or 'usb' not in str((disk/'device').resolve()):continue
    result['storage'].append({'device':'/dev/'+disk.name,'path':str((disk/'device').resolve()),'bytes':int((disk/'size').read_text())*512})
print(json.dumps(result,indent=2))
