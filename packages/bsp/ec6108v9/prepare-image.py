#!/usr/bin/env python3
"""Prepare the mounted Armbian filesystem and its appended-DTB kernel."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from uimage import make_image, validate_image


def prepare(root, staging, source, version):
    root = root.resolve()
    if root == Path("/") or not (root / "etc/armbian-release").is_file():
        raise ValueError("Expected a separate Armbian image filesystem")
    board = json.loads((source / "config/boards/ec6108v9.json").read_text())
    info = json.loads((source / "config/sources/linux-hi3798mv100.json").read_text())
    modules = [path for path in (root / "lib/modules").iterdir() if path.is_dir()]
    if len(modules) != 1:
        raise ValueError("Exactly one installed kernel is required")
    release = modules[0].name
    kernel = root / "boot" / ("vmlinuz-" + release)
    # ARM32 dtbs_install flattens the vendor directory in this kernel.
    dtbs = [directory / relative
            for directory in (root / "boot" / ("dtb-" + release),
                              root / "usr/lib" / ("linux-image-" + release))
            for relative in (board["dtb_target"], Path(board["dtb_target"]).name)]
    dtb = next((path for path in dtbs if path.is_file()), None)
    if not kernel.is_file() or dtb is None:
        raise ValueError("Installed kernel or EC6108V9 DTB is missing; checked: " +
                         ", ".join(map(str, [kernel, *dtbs])))
    for name, expected in (("mmc0", "/soc@f0000000/ahb/mmc@9830000"),
                           ("mmc1", "/soc@f0000000/ahb/mmc@9820000")):
        actual = subprocess.check_output(["fdtget", str(dtb), "/aliases", name], text=True).strip()
        if actual != expected:
            raise ValueError("Compiled DTB has an unsafe storage alias: " + name)
    image = make_image(kernel.read_bytes(), dtb.read_bytes(), release, info["source_date_epoch"],
                       board["kernel_load_address"], board["kernel_read_bytes"])
    validate_image(image, board["kernel_read_bytes"])
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "uImage").write_bytes(image)
    metadata = {"release": version, "kernel_release": release, "kernel_bytes": len(image),
                "kernel_sha256": hashlib.sha256(image).hexdigest(),
                "source": info, "framework": json.loads((source / "config/sources/armbian-build.json").read_text()),
                "tested_boot": False, "private_device_configuration": False}
    (staging / "image.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (root / "usr/share/ec6108v9").mkdir(parents=True, exist_ok=True)
    (root / "usr/share/ec6108v9/release.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (root / "etc/fstab").write_text(
        "/dev/mmcblk0p3 / ext4 defaults,noatime 0 1\n"
        "/dev/mmcblk1p1 /mnt/sdcard auto defaults,noatime,nosuid,nodev,nofail,"
        "x-systemd.automount,x-systemd.device-timeout=5s,x-systemd.mount-timeout=30s 0 0\n")
    (root / "mnt/sdcard").mkdir(parents=True, exist_ok=True)
    for name in ("etc/machine-id", "var/lib/dbus/machine-id"):
        path = root / name
        path.unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
    (root / "etc/machine-id").write_text("")
    (root / "var/lib/dbus/machine-id").symlink_to("/etc/machine-id")
    for path in (root / "etc/ssh").glob("ssh_host_*"):
        path.unlink()
    for name in ("root/.ssh", "var/lib/ec6108v9", "etc/ec6108-system.json",
                 "etc/wpa_supplicant/wpa_supplicant-wlan0.conf"):
        path = root / name
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    for path in (root / "etc/NetworkManager/system-connections").glob("*"):
        if path.is_file() or path.is_symlink():
            path.unlink()
    # These files are unused by this bootloader. Keep the kernel and DTB for inspection.
    for pattern in ("initrd.img*", "uInitrd*", "boot.scr*", "boot.cmd", "armbianEnv.txt"):
        for path in (root / "boot").glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink()
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
