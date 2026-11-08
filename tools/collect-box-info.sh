#!/bin/sh
# Read-only diagnostics for planning an EC6108V9 Armbian port.
# Run this on the box, or pipe it to its SSH session. Output goes to stdout.

section() {
    printf '\n## %s\n' "$1"
}

section 'Kernel and userspace architecture'
uname -a
if command -v dpkg >/dev/null 2>&1; then
    dpkg --print-architecture
fi
if [ -r /etc/os-release ]; then
    cat /etc/os-release
fi

section 'CPU'
if [ -r /proc/cpuinfo ]; then
    # Omit per-device serial numbers.
    grep -Ei '^(processor|model name|cpu architecture|hardware|revision)[[:space:]]*:' /proc/cpuinfo
fi

section 'Device tree model'
if [ -r /sys/firmware/devicetree/base/model ]; then
    tr '\000' '\n' < /sys/firmware/devicetree/base/model
else
    printf 'No device tree model exposed\n'
fi

section 'Boot arguments and partition layout'
if [ -r /proc/cmdline ]; then
    cat /proc/cmdline
fi
if [ -r /proc/partitions ]; then
    cat /proc/partitions
fi
if command -v lsblk >/dev/null 2>&1; then
    lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
fi
if command -v findmnt >/dev/null 2>&1; then
    findmnt -n -o SOURCE,FSTYPE,OPTIONS /
fi

section 'Installed kernel module directories'
for module_dir in /lib/modules/*; do
    [ -d "$module_dir" ] || continue
    printf '%s\n' "$module_dir"
done

section 'Loaded modules'
if [ -r /proc/modules ]; then
    cat /proc/modules
fi

section 'Kernel config required for rootfs migration'
config_pattern='^(CONFIG_(AEABI|VFP|DEVTMPFS|DEVTMPFS_MOUNT|BLK_DEV_INITRD|BLK_DEV_LOOP|EXT4_FS|USB_STORAGE|MMC|CGROUPS|NAMESPACES|SECCOMP|FHANDLE|TMPFS|OVERLAY_FS|BLK_DEV_DM|SECURITY|NETFILTER|IP_NF_IPTABLES|NF_TABLES)=|# CONFIG_(BLK_DEV_INITRD|CGROUPS|NAMESPACES|SECCOMP|FHANDLE|OVERLAY_FS|NF_TABLES) is not set)'
if [ -r /proc/config.gz ] && command -v zcat >/dev/null 2>&1; then
    zcat /proc/config.gz | grep -E "$config_pattern"
elif [ -r "/boot/config-$(uname -r)" ]; then
    grep -E "$config_pattern" "/boot/config-$(uname -r)"
else
    printf 'Kernel config is not exposed\n'
fi

section 'Memory and root filesystem capacity'
if [ -r /proc/meminfo ]; then
    grep -E '^(MemTotal|MemAvailable|SwapTotal):' /proc/meminfo
fi
df -h /

section 'Done'
printf 'Only diagnostic reads were performed. No partitions or settings were changed.\n'
