#!/usr/bin/env python3
"""Prepare the mounted Armbian filesystem and its appended-DTB kernel."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import json
from pathlib import Path
import shutil
from kernel_package import assemble


def prepare(root, staging, source, version):
    root = root.resolve()
    board = json.loads((source / "config/boards/ec6108v9.json").read_text())
    info = json.loads((source / "config/sources/linux-hi3798mv100.json").read_text())
    image, kernel, _ = assemble(root, board, info["source_date_epoch"])
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "uImage").write_bytes(image)
    metadata = {"release": version, **kernel,
                "source": info, "framework": json.loads((source / "config/sources/armbian-build.json").read_text()),
                "tested_boot": False, "private_device_configuration": False}
    (staging / "image.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (root / "usr/share/ec6108v9").mkdir(parents=True, exist_ok=True)
    (root / "usr/share/ec6108v9/release.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (root / "etc/fstab").write_text("/dev/mmcblk0p3 / ext4 defaults,noatime 0 1\n")
    for name in ("etc/machine-id", "var/lib/dbus/machine-id"):
        path = root / name
        path.unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
    (root / "etc/machine-id").write_text("")
    (root / "var/lib/dbus/machine-id").symlink_to("/etc/machine-id")
    for path in (root / "etc/ssh").glob("ssh_host_*"):
        path.unlink()
    for name in ("root/.ssh", "var/lib/ec6108v9", "etc/ec6108-system.json"):
        path = root / name
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    for pattern in ("etc/NetworkManager/system-connections/*", "etc/wpa_supplicant/*.conf"):
        for path in root.glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink()
    # These files are unused by this bootloader. Keep the kernel and DTB for inspection.
    for pattern in ("initrd.img*", "uInitrd*", "boot.scr*", "boot.cmd", "armbianEnv.txt"):
        for path in (root / "boot").glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink()
    # The framework's final initramfs chroot can repopulate these download caches.
    for name in ("var/lib/apt/lists", "var/cache/apt/archives"):
        directory = root / name
        if directory.exists():
            for path in directory.iterdir():
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        (directory / "partial").mkdir(parents=True, exist_ok=True)
    if (root / "etc/machine-id").read_bytes() or list((root / "etc/ssh").glob("ssh_host_*_key")):
        raise ValueError("Per-device identity remained in the image")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "staging", "source-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.staging, args.source_root, args.version), indent=2))
