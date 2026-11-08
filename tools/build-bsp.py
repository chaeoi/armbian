#!/usr/bin/env python3
"""Adapt official Armbian CLI components for the EC6108V9 boot layout."""

import hashlib
from pathlib import Path
import shutil
import subprocess


def main():
    project = Path(__file__).resolve().parent.parent
    source = project / "downloads/armbian-bsp-cli-orangepione-current_26.8.3_armhf__1-PCf201-V3741-H9299-B3f34-R7cb5.deb"
    expected = "90f43149a63566a07ecf225441d4fee446c0dff147f37777c7e581d3ae8bc037"
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise RuntimeError("Official BSP package does not match the pinned digest")
    package = project / "work/armbian-bsp-ec6108v9"
    if package.exists():
        shutil.rmtree(package)
    subprocess.run(["dpkg-deb", "-R", str(source), str(package)], check=True)

    # These components encode another board's flash layout or boot protocol.
    excluded = [
        "etc/fw_env.config", "etc/initramfs", "etc/kernel",
        "usr/share/initramfs-tools", "usr/share/armbian/boot.cmd",
        "usr/share/armbian/armbianEnv.txt", "usr/bin/armbian-install",
        "usr/bin/armbian-upgrade", "usr/sbin/armbian-add-overlay", "usr/sbin/ddbr",
    ]
    for relative in excluded:
        path = package / relative
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    (package / "etc/armbian-release").write_text('''# Local EC6108V9 Armbian port
BOARD=ec6108v9
BOARD_NAME="Huawei EC6108V9"
BOARDFAMILY=histb
LINUXFAMILY=hi3798mv100
ARCH=arm
INITRD_ARCH=arm
KERNEL_IMAGE_TYPE=uImage
KERNEL_TARGET=custom
KERNEL_TEST_TARGET=custom
IMAGE_TYPE=user-built
BOARD_TYPE=csc
VENDOR="Armbian"
VENDORCOLOR="247;16;0"
VENDORDOCS="https://docs.armbian.com"
VENDORURL="https://www.armbian.com"
BUILD_REPOSITORY_URL=https://github.com/armbian/build
BUILD_REPOSITORY_COMMIT=fd4ebfd1e
VERSION=26.8.3+ec6108v9.1
REVISION=26.8.3+ec6108v9.1
''')
    control = package / "DEBIAN"
    for path in control.iterdir():
        if path.name not in ("control", "changelog"):
            path.unlink()
    (control / "control").write_text('''Package: armbian-bsp-cli-ec6108v9
Version: 26.8.3+ec6108v9.1
Architecture: armhf
Maintainer: Local EC6108V9 Port <root@localhost>
Section: admin
Priority: optional
Depends: bash, lsb-release
Provides: armbian-bsp-cli
Description: Armbian CLI components adapted for EC6108V9
 Based on official Armbian 26.8.3 CLI components. Boot and kernel
 installation are handled by the EC6108V9 port's dedicated tooling.
''')
    postinst = control / "postinst"
    postinst.write_text('''#!/bin/sh
set -eu
for name in motd ramlog zram-config firstrun; do
    if [ ! -f "/etc/default/armbian-$name" ] && [ -f "/etc/default/armbian-$name.dpkg-dist" ]; then
        cp "/etc/default/armbian-$name.dpkg-dist" "/etc/default/armbian-$name"
    fi
done
# Keep hardware and disk changes disabled during initial port validation.
for name in hardware-monitor hardware-optimize zram-config ramlog firstrun resize-filesystem led-state; do
    systemctl --root=/ mask "armbian-$name.service" >/dev/null 2>&1 || true
done
ln -sfn /var/run/motd /etc/motd
rm -f /root/.not_logged_in
exit 0
''')
    postinst.chmod(0o755)
    documentation = package / "usr/share/doc/armbian-bsp-cli-ec6108v9"
    documentation.mkdir(parents=True)
    (documentation / "README").write_text(
        "Locally adapted from the official Armbian CLI BSP 26.8.3.\n"
        "Source: https://github.com/armbian/build (fd4ebfd1e)\n"
        "Original package SHA256: " + expected + "\n"
        "This is a community port, not an officially supported Armbian board.\n"
        "Excluded: other-board boot scripts, flash installers, environment offsets,\n"
        "kernel/initramfs hooks. Hardware setup services remain masked until tested.\n"
    )
    output = project / "output"
    output.mkdir(exist_ok=True)
    destination = output / "armbian-bsp-cli-ec6108v9_26.8.3+ec6108v9.1_armhf.deb"
    subprocess.run([
        "dpkg-deb", "--root-owner-group", "--build", str(package), str(destination)
    ], check=True)
    print(destination)


if __name__ == "__main__":
    main()
