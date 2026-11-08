#!/bin/sh
set -u
failed=0
check() {
    label=$1
    shift
    printf '\nTEST %s\n' "$label"
    if "$@"; then printf 'PASS %s\n' "$label"; else code=$?; printf 'FAIL %s exit=%s\n' "$label" "$code"; failed=$((failed+1)); fi
}
check kernel uname -a
check root findmnt /
check ssh /usr/sbin/sshd -t
check packages dpkg --audit
check dependencies apt-get check
check modules sh -ec 'for module in exfat nls_utf8 rtl8xxxu veth bridge br_netfilter overlay fuse autofs4 nf_tables nf_conntrack nf_nat nft_ct nft_nat nft_masq nft_compat iptable_filter iptable_nat xt_conntrack xt_addrtype xt_MASQUERADE xt_nat xt_tcpudp; do modprobe "$module"; done'
check namespaces unshare --mount --net --uts --ipc --pid --fork sh -ec 'ip link set lo up; ip link add audit0 type veth peer name audit1; ip link add auditbr type bridge; ip link set audit0 master auditbr; ip link set audit0 up; ip link set audit1 up; ping -6 -c 2 ::1; test "$$" = 1; ip -br link'
check overlay sh -ec 'scratch=$(mktemp -d /run/ec6108-overlay.XXXXXX); mkdir "$scratch/lower" "$scratch/upper" "$scratch/work" "$scratch/merged"; trap '\''umount "$scratch/merged" 2>/dev/null; rm -rf "$scratch"'\'' EXIT; printf base > "$scratch/lower/file"; mount -t overlay overlay -o "lowerdir=$scratch/lower,upperdir=$scratch/upper,workdir=$scratch/work" "$scratch/merged"; test "$(cat "$scratch/merged/file")" = base; printf changed > "$scratch/merged/file"; test "$(cat "$scratch/upper/file")" = changed; test "$(cat "$scratch/lower/file")" = base'
check cgroup systemd-run --quiet --wait --pipe --unit=ec6108-audit-cgroup -p MemoryMax=32M -p TasksMax=16 /bin/sh -ec 'cat /proc/self/cgroup; dd if=/dev/zero of=/dev/null bs=1M count=8 status=none'
check ipv4-ethernet ping -I eth0 -c 10 -W 2 10.42.0.1
check ipv4-wifi ping -I wlan0 -c 10 -W 2 192.168.10.1
check ipv6 ping -6 -c 3 ::1
check dns timeout 20 resolvectl query ports.ubuntu.com
check https curl --connect-timeout 10 --max-time 25 -I -fsS https://ports.ubuntu.com/ubuntu-ports/
check ntp sh -ec 'timedatectl; test "$(timedatectl show -p NTPSynchronized --value)" = yes'
check wifi-powersave sh -ec 'iw dev wlan0 get power_save | grep -q "Power save: off"; systemctl is-active ec6108-wifi-power-save-off.service'
check random python3 -c 'import os,time; t=time.monotonic(); b=os.urandom(1048576); assert len(b)==1048576 and len(set(b))==256; print("1MiB getrandom in",round(time.monotonic()-t,3),"seconds")'
check journal sh -ec 'logger -t ec6108-audit audit-journal-check; sleep 1; journalctl -b -t ec6108-audit --no-pager | grep audit-journal-check'
check boot-health /usr/local/sbin/ec6108-accept-boot
check services sh -ec 'systemctl is-system-running; test "$(systemctl --failed --no-legend | wc -l)" = 0'
printf '\nFailed tests: %s\n' "$failed"
exit "$failed"
