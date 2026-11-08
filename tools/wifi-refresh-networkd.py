#!/usr/bin/env python3
"""Refresh networkd's cached nl80211 family after the Wi-Fi core is reloaded."""
import argparse
import fcntl
from pathlib import Path
import socket
import struct
import subprocess


def family_id():
    name=b'nl80211\0'
    attr=struct.pack('HH',len(name)+4,2)+name
    attr+=bytes((-len(attr))%4)
    request=struct.pack('IHHII',20+len(attr),0x10,1,1,0)+bytes([3,2,0,0])+attr
    with socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,16) as sock:
        sock.settimeout(3)
        sock.bind((0,0))
        sock.sendto(request,(0,0))
        while True:
            data=sock.recv(65536)
            offset=0
            while offset+16<=len(data):
                length,kind,flags,sequence,pid=struct.unpack_from('IHHII',data,offset)
                if length<16 or offset+length>len(data):raise RuntimeError('Invalid netlink reply')
                if sequence==1:
                    if kind==2:
                        error=struct.unpack_from('i',data,offset+16)[0]
                        if error:raise OSError(-error,'nl80211 family lookup failed')
                    elif kind==0x10:
                        pos=offset+20
                        while pos+4<=offset+length:
                            size,attr_kind=struct.unpack_from('HH',data,pos)
                            if size<4 or pos+size>offset+length:raise RuntimeError('Invalid family attribute')
                            if attr_kind&0x3fff==1:return struct.unpack_from('H',data,pos+4)[0]
                            pos+=(size+3)&~3
                offset+=(length+3)&~3


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',action='store_true')
    args=parser.parse_args()
    current=family_id()
    if args.probe:
        print(current)
        return
    with open('/run/ec6108-wifi-family.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=Path('/run/ec6108-wifi-family')
        previous=int(state.read_text()) if state.exists() else None
        if previous is not None and previous!=current:
            # v249 keeps a stale generic-netlink ID when cfg80211 is removed.
            # Restart only when that ID changes, leaving normal reconnects alone.
            subprocess.run(['systemctl','try-restart','systemd-networkd.service'],check=True)
            print('Refreshed networkd after nl80211 family changed: {} -> {}'.format(previous,current))
        state.write_text(str(current)+'\n')


if __name__=='__main__':main()
