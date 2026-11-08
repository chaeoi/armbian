#!/usr/bin/env python3
"""Assemble the private, directly installed EC6108V9 release around an exported rootfs."""
import hashlib
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--private', action='store_true',
                    help='Explicitly build a package containing this device\'s private configuration')
parser.add_argument('--sd-uuid', help='Optional exFAT SD UUID; omit to leave SD unconfigured')
args = parser.parse_args()
if not args.private:
    parser.error('This exports device identities and credentials; use --private for a private backup only')
if args.sd_uuid:
    import re
    if not re.fullmatch(r'[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}', args.sd_uuid):
        parser.error('--sd-uuid must be an exFAT UUID, for example ABCD-1234')
project=Path(__file__).resolve().parent.parent
dest=project/'output/ec6108v9-armbian-r6-single'
dest.mkdir(mode=0o700,exist_ok=True)
os.chmod(dest,0o700)
rootfs=dest/'rootfs.tar.gz'
assert rootfs.exists() and rootfs.stat().st_size>20*1024*1024,'Export the clean rootfs first'
kernel=json.loads((project/'output/kernel-manifest.json').read_text())
if not kernel.get('tested_boot'):
    raise SystemExit('Kernel has no recorded boot validation; keep it separate from the private reinstall package')
previous=json.loads((dest/'manifest.json').read_text()) if (dest/'manifest.json').exists() else {}
shutil.copy2(project/'output/uImage-ec6108v9',dest/'uImage')
for source,target in [('ec6108-ram-init.sh','ram-init.sh'),('prepare-direct-install.py','prepare-install.py'),
                      ('install-direct-in-ram.py','install-in-ram.py'),('flash-direct.py','flash.py')]:
    shutil.copy2(project/'tools'/source,dest/target)
manifest={'release':'ec6108v9-armbian-26.8.3-r6-single-20261108',
          'kernel_release':kernel['kernel_release'],'kernel_bytes':kernel['image_bytes'],
          'kernel_sha256':kernel['sha256'],'root_uuid':previous.get('root_uuid',str(uuid.uuid4())),
          'emmc_bytes':3959422976,'root_offset':34*1024*1024,
          'rootfs_sha256':hashlib.sha256(rootfs.read_bytes()).hexdigest(),
          'rootfs_bytes':rootfs.stat().st_size,'single_os':True,'fallback':False,
          'source_commit':kernel['source']['commit'],'private_device_configuration':True,
          'wifi_shutdown_cleanup':True}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
unit='''[Unit]
Description=Verify the fixed EC6108V9 Armbian installation
Requires=ssh.service
After=ssh.service
ConditionPathExists=/etc/ec6108-system.json
ConditionPathExists=!/etc/ec6108-ram-mode

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ec6108-verify-system
RemainAfterExit=yes
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
'''
fstab='UUID='+manifest['root_uuid']+' / ext4 defaults,noatime 0 1\n'
if args.sd_uuid:
    fstab += ('UUID='+args.sd_uuid+' /mnt/sdcard exfat defaults,noatime,nosuid,nodev,nofail,'
              'x-systemd.automount,x-systemd.device-timeout=5s,x-systemd.mount-timeout=30s 0 0\n')
files={'etc/fstab':(fstab.encode(),0o644),
       'etc/systemd/system/ec6108-system-check.service':(unit.encode(),0o644),
       'usr/local/sbin/ec6108-verify-system':((project/'tools/verify-direct-system.py').read_bytes(),0o755),
       'usr/lib/systemd/system-shutdown/ec6108-wifi-reset':((project/'tools/wifi-clean-shutdown.sh').read_bytes(),0o755),
       'etc/ec6108-frozen-release':((manifest['release']+'\n').encode(),0o644)}
with tarfile.open(dest/'overlay.tar','w') as archive:
    for name,(content,mode) in files.items():
        entry=tarfile.TarInfo(name);entry.size=len(content);entry.mode=mode;entry.uid=entry.gid=0
        archive.addfile(entry,io.BytesIO(content))
    entry=tarfile.TarInfo('etc/systemd/system/multi-user.target.wants/ec6108-system-check.service')
    entry.type=tarfile.SYMTYPE;entry.linkname='../ec6108-system-check.service';entry.mode=0o777
    archive.addfile(entry)
names=['rootfs.tar.gz','overlay.tar','uImage','manifest.json','ram-init.sh','prepare-install.py','install-in-ram.py']
(dest/'SHA256SUMS').write_text(''.join(hashlib.sha256((dest/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in names))
connection=json.loads((project/'artifacts/connection.json').read_text())
shutil.copy2(project/'artifacts/ec6108-management-key',dest/'management-key')
with tarfile.open(rootfs) as archive:
    public=archive.extractfile('./etc/ssh/ssh_host_ed25519_key.pub').read().decode().split()
(dest/'known_hosts').write_text('ec6108v9-armbian-private '+public[0]+' '+public[1]+'\n')
(dest/'connection.json').write_text(json.dumps({'host':connection['host'],
    'identity':'management-key','known_hosts':'known_hosts','host_key_alias':'ec6108v9-armbian-private'},indent=2)+'\n')
(dest/'flash.sh').write_text('#!/bin/sh\nset -eu\ncd -- "$(dirname -- "$0")"\nexec python3 ./flash.py --flash "$@"\n')
(dest/'flash.sh').chmod(0o700)
(dest/'README.md').write_text('''# EC6108V9 Armbian 单系统私有刷机包

目标为本次实测的 EC6108V9、Hi3798MV100、1 GiB RAM、3,959,422,976 字节 eMMC，以及已核实的引导位置。支持本机旧布局和新的三分区布局。

在本机运行 `./flash.sh`，会核对文件摘要及硬件，进入 RAM 系统，将 eMMC 的原恢复、备份和系统区合并为一个 Armbian 根分区，安装 r6 内核并设为固定启动。安装会删除内置存储上的原系统及其文件；最终没有海 NAS 或系统回退入口。USB 和 SD 不在刷写目标内。

仅检查可用 `python3 flash.py`。连接配置位于 connection.json；移动到另一电脑时，可传入 --host、--identity、--known-hosts。需要目标已能通过 SSH 连接且具有 root 权限；空白或完全无法启动的设备不能通过此网络安装程序刷写。

这是本机私有配置包，包含 SSH 登录密钥、现有 SSH 主机身份、登录配置和 Wi-Fi 配置，应按私有备份保存，不适合作为公开通用镜像分发。SSH 登录私钥只在电脑端安装包内，没有放入系统镜像。

安装时会先进入临时 RAM 系统，首次校验和解包实测约四分钟，安装器等待上限为十分钟。正式系统开机不需要解包。网络中断后可再次运行脚本，安装器会检查 RAM 中的现有安装状态。

包含无线关机清理：重启前卸载 rtl8xxxu，调用驱动现有的芯片关断与复位流程，避免芯片带着旧固件状态进入下一次启动。

布局：p1 为 14 MiB 引导与参数区，p2 为 20 MiB 内核区，p3 从 34 MiB 到 eMMC 末尾，单一 ext4 Armbian 根系统。引导程序为芯片启动所需，不构成第二套操作系统。
''')
for path in dest.iterdir():
    if path.is_file() and path.name!='flash.sh':path.chmod(0o600)
print(json.dumps(manifest,indent=2))
