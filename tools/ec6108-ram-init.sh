#!/bin/sh
# Enter a complete Armbian system in RAM before replacing the eMMC filesystem.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
test "$$" = 1
mount --make-rprivate /
mount -o remount,rw /
mountpoint -q /proc || mount -t proc proc /proc
mountpoint -q /sys || mount -t sysfs sysfs /sys
mountpoint -q /dev || mount -t devtmpfs devtmpfs /dev
mountpoint -q /run || mount -t tmpfs -o mode=755,nosuid,nodev tmpfs /run
stage=/var/lib/ec6108-install
cd "$stage"
sha256sum -c SHA256SUMS
mkdir -p /mnt/ec6108-ramroot
mount -t tmpfs -o size=750M,mode=755 tmpfs /mnt/ec6108-ramroot
newroot=/mnt/ec6108-ramroot
tar --numeric-owner --xattrs --acls -xzf rootfs.tar.gz -C "$newroot"
tar --numeric-owner -xf overlay.tar -C "$newroot"
mkdir -p "$newroot/opt/ec6108-install" "$newroot/.oldroot"
cp uImage manifest.json install-in-ram.py prepare-install.py "$newroot/opt/ec6108-install/"
cp "$newroot/etc/fstab" "$newroot/opt/ec6108-install/fstab.target"
printf 'tmpfs / tmpfs defaults,noatime 0 0\n' > "$newroot/etc/fstab"
touch "$newroot/etc/ec6108-ram-mode"
rm -f "$newroot/etc/systemd/system/multi-user.target.wants/ec6108-accept-boot.service"
rm -f "$newroot/etc/systemd/system/ec6108-accept-boot.service" "$newroot/usr/local/sbin/ec6108-accept-boot"
rm -f "$newroot/etc/armbian-ec6108v9-boot.json"
mkdir -p "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run"
cd "$newroot"
mount --move /dev dev
mount --move /proc proc
mount --move /sys sys
mount --move /run run
pivot_root . .oldroot
cd /
exec /sbin/init
