#!/usr/bin/env python3
"""Run the pinned official Armbian framework with the EC6108V9 overlay."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from port import PROJECT


def prepare(destination):
    specification = json.loads((PROJECT / "config/sources/armbian-build.json").read_text())
    if not destination.exists():
        destination.mkdir(parents=True)
        subprocess.run(["git", "-C", str(destination), "init", "--quiet"], check=True)
        subprocess.run(["git", "-C", str(destination), "remote", "add", "origin",
                        specification["repository"]], check=True)
        subprocess.run(["git", "-C", str(destination), "fetch", "--depth=1", "origin",
                        specification["commit"]], check=True)
        subprocess.run(["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"], check=True)
    actual = subprocess.check_output(["git", "-C", str(destination), "rev-parse", "HEAD"], text=True).strip()
    if actual != specification["commit"]:
        raise RuntimeError("Armbian framework commit differs; select an empty ARMBIAN_BUILD_DIR")
    files = ["config/boards/ec6108v9.tvb", "config/boards/ec6108v9.json",
             "config/kernel/linux-hi3798mv100-edge.config",
             "config/sources/armbian-build.json", "config/sources/linux-hi3798mv100.json",
             "config/sources/families/hi3798mv100.conf", "config/sources/usb-bootstrap.json",
             "config/sources/ec6108v9-firmware.json", "extensions/ec6108v9-usb.sh"]
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT / name, target)
    for name in ("packages/bsp/ec6108v9", "packages/blobs/hi3798mv100/mdmo1d",
                 "packages/blobs/hi3798mv100/firmware"):
        shutil.copytree(PROJECT / name, destination / name, dirs_exist_ok=True)
    patch_dir = destination / "patch/kernel/archive/hi3798mv100-7.3"
    patch_dir.mkdir(parents=True, exist_ok=True)
    for directory in (PROJECT / "patch/kernel/hi3798mv100",
                      PROJECT / "patch/kernel/archive/hi3798mv100-7.3"):
        for path in directory.glob("*.patch"):
            shutil.copy2(path, patch_dir / path.name)
    helpers = destination / "packages/bsp/ec6108v9"
    for name in ("uimage.py", "wifi-refresh-networkd.py", "wifi-clean-shutdown.sh",
                 "fix-system-config.py", "verify-direct-system.py"):
        shutil.copy2(PROJECT / "tools" / name, helpers / name)
    return specification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    destination = Path(os.environ.get("ARMBIAN_BUILD_DIR", PROJECT / "work/armbian-build")).expanduser().resolve()
    prepare(destination)
    print("Prepared official Armbian framework:", destination, flush=True, file=sys.stderr)
    if args.prepare_only:
        return
    arguments = args.arguments or ["build"]
    if arguments[0].startswith("BOARD="):
        arguments.insert(0, "build")
    defaults = ["BOARD=ec6108v9", "BRANCH=edge", "RELEASE=jammy", "BUILD_MINIMAL=yes",
                "BUILD_DESKTOP=no", "KERNEL_CONFIGURE=no", "EXPERT=yes",
                "INSTALL_ARMBIAN_FIRMWARE=no", "INSTALL_HEADERS=no", "NETWORKING_STACK=systemd-networkd",
                "COMPRESS_OUTPUTIMAGE=sha,xz",
                "VENDOR=Armbian-unofficial", "MAINTAINER=canghai0823", "MAINTAINERMAIL=canghai0823@users.noreply.github.com",
                "FINALDEST=" + str(PROJECT / "output/images")]
    specified = {argument.split("=", 1)[0] for argument in arguments if "=" in argument}
    defaults = [argument for argument in defaults if argument.split("=", 1)[0] not in specified]
    environment = os.environ.copy()
    if arguments[0] in {"config-dump-json", "artifact-config-dump-json"}:
        # Native CI logging otherwise prefixes stdout with a GitHub ::group:: marker.
        environment.update(CONFIG_DEFS_ONLY="yes", CI="false")
    os.execve(str(destination / "compile.sh"),
              [str(destination / "compile.sh"), *arguments, *defaults], environment)


if __name__ == "__main__":
    main()
