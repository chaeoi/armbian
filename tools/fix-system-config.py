#!/usr/bin/env python3
"""Apply the EC6108V9 compatibility settings validated by the system audit."""
from pathlib import Path
import os
import re
import subprocess

root = Path(os.environ.get('ARMBIAN_ROOT', '/'))
def write(relative, text, mode=0o644):
    p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(mode)
write('etc/modules-load.d/rtl8xxxu.conf','rtl8xxxu\n')
helper=Path(__file__).with_name('wifi-refresh-networkd.py')
write('usr/local/sbin/ec6108-wifi-refresh-networkd',helper.read_text(),0o755)
p=root/'etc/udev/rules.d/10-wifi-disable-powermanagement.rules'
if p.exists() and not p.is_symlink():
    backup=p.with_suffix('.rules.staging-backup')
    if not backup.exists():p.rename(backup)
    else:p.unlink()
write('etc/udev/rules.d/10-wifi-disable-powermanagement.rules',
      '# Power saving is configured by ec6108-wifi-power-save-off.service.\n')
write('usr/local/sbin/ec6108-wifi-power-save-off', '''#!/bin/sh
set -eu
/usr/local/sbin/ec6108-wifi-refresh-networkd
power_disabled=0
link_failed=0
for attempt in $(seq 1 30); do
    if /sbin/iw dev wlan0 get power_save 2>/dev/null | /bin/grep -q 'Power save: off'; then
        power_disabled=1
    elif /sbin/iw dev wlan0 set power_save off 2>/dev/null; then
        power_disabled=1
    fi
    if [ "$power_disabled" = 1 ] && /sbin/wpa_cli -i wlan0 status 2>/dev/null | /bin/grep -q '^wpa_state=COMPLETED$'; then
        index=$(cat /sys/class/net/wlan0/ifindex)
        state=/run/systemd/netif/links/$index
        if /bin/grep -q '^ADMIN_STATE=failed$' "$state" 2>/dev/null; then
            link_failed=1
            /usr/bin/networkctl reconfigure wlan0
        elif /bin/grep -Eq '^(ADMIN_STATE=configured|IPV4_ADDRESS_STATE=routable|IPV6_ADDRESS_STATE=routable)$' "$state" 2>/dev/null; then
            exit 0
        fi
    fi
    sleep 1
done
# An unavailable access point must not turn power setup into a failed service.
test "$power_disabled" = 1 && test "$link_failed" = 0
''',0o755)
write('etc/systemd/system/ec6108-wifi-power-save-off.service','''[Unit]
Description=Configure EC6108V9 Wi-Fi and recover its link after device setup
BindsTo=sys-subsystem-net-devices-wlan0.device
Wants=wpa_supplicant@wlan0.service
After=sys-subsystem-net-devices-wlan0.device wpa_supplicant@wlan0.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ec6108-wifi-power-save-off
RemainAfterExit=yes
TimeoutStartSec=45
''')
write('etc/udev/rules.d/90-ec6108-wifi.rules','''ACTION=="add", SUBSYSTEM=="net", KERNEL=="wlan0", TAG+="systemd", ENV{SYSTEMD_WANTS}+="wpa_supplicant@wlan0.service ec6108-wifi-power-save-off.service"
''')
write('etc/systemd/system/wpa_supplicant@wlan0.service.d/10-ec6108-device.conf','''[Unit]
BindsTo=sys-subsystem-net-devices-wlan0.device
After=sys-subsystem-net-devices-wlan0.device

[Service]
Restart=on-failure
RestartSec=2
''')
for name in ('10-ethernet.network','20-wifi.network'):
    path=root/'etc/systemd/network'/name
    if not path.exists():continue
    text=path.read_text()
    if '[DHCPv4]' not in text:text+='\n[DHCPv4]\n'
    if not re.search(r'^UseHostname=no$',text,re.M):
        text=text.replace('[DHCPv4]','[DHCPv4]\nUseHostname=no',1)
    path.write_text(text);path.chmod(0o644)
for name in ('syslog.socket','systemd-journald.socket','systemd-journald-dev-log.socket'):
    write('etc/systemd/system/'+name+'.d/10-ec6108-compat.conf','[Socket]\nPassSecurity=no\n')
unit=root/'etc/systemd/system/ec6108-accept-boot.service'
if unit.exists():unit.chmod(0o644)
p=root/'var/log/journal'
if p.is_symlink():p.unlink()
p.mkdir(exist_ok=True)
p.chmod(0o2755)
groups=(root/'etc/group').read_text().splitlines()
journal_gid=next(int(line.split(':')[2]) for line in groups if line.startswith('systemd-journal:'))
os.chown(p,0,journal_gid)
if root==Path('/'):
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['udevadm','control','--reload-rules'],check=True)
    subprocess.run(['networkctl','reload'],check=True)
    subprocess.run(['systemctl','start','ec6108-wifi-power-save-off.service'],check=True)
print('Corrected module loading, Wi-Fi startup ordering, DHCP hostname policy, journal sockets and unit permissions.')
