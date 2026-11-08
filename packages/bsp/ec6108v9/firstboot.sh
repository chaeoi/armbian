#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
state=/var/lib/ec6108v9
test -e "$state/initialized" && exit 0
test "$(findmnt -n -o SOURCE /)" = /dev/mmcblk0p3
test "$(cat /sys/class/block/mmcblk0/device/type)" = MMC
test "$(cat /sys/class/block/mmcblk0/size)" = 7733248
resize2fs /dev/mmcblk0p3
ssh-keygen -A
python3 - <<'PY'
import hashlib,json,os,subprocess,time
from pathlib import Path
cid=Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()
address='02:'+':'.join(hashlib.sha256(cid.encode()).hexdigest()[i:i+2] for i in range(0,10,2))
link=Path('/etc/systemd/network/05-ec6108v9-ethernet.link')
link.write_text('[Match]\nOriginalName=eth*\n\n[Link]\nNamePolicy=\nName=eth0\nMACAddress='+address+'\n')
for attempt in range(30):
    if Path('/sys/class/net/eth0').exists():break
    time.sleep(1)
subprocess.run(['ip','link','set','dev','eth0','address',address],check=True)
release=json.loads(Path('/usr/share/ec6108v9/release.json').read_text())
with open('/dev/mmcblk0','rb') as stream:
    stream.seek(1024*1024)
    environment=stream.read(1024*1024)
config={'kernel_release':release['kernel_release'],'kernel_bytes':release['kernel_bytes'],
        'kernel_sha256':release['kernel_sha256'],
        'root_uuid':subprocess.check_output(['blkid','-s','UUID','-o','value','/dev/mmcblk0p3'],text=True).strip(),
        'root_offset':34*1024*1024,'emmc_cid':cid,
        'environment_sha256':hashlib.sha256(environment).hexdigest(),
        'installation':'single-armbian-direct-emmc'}
Path('/etc/ec6108-system.json').write_text(json.dumps(config,indent=2)+'\n')
packages=[]
for stanza in Path('/var/lib/dpkg/status').read_text().split('\n\n'):
    fields=dict(line.split(': ',1) for line in stanza.splitlines() if ': ' in line and not line.startswith(' '))
    name=fields.get('Package','')
    if fields.get('Status')=='install ok installed' and (
            (name.startswith(('linux-image-','linux-dtb-')) and 'hi3798mv100' in name) or
            name.startswith('armbian-bsp-cli-ec6108v9')):
        packages.append(name)
if packages:subprocess.run(['apt-mark','hold',*packages],check=True)
PY
mkdir -p "$state"
touch "$state/initialized"
