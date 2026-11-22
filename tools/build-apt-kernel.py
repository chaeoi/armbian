#!/usr/bin/env python3
"""Package the EC6108V9 kernel and modules from a verified USB image."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from port import BOARD, PROJECT

BSP = PROJECT / "packages/bsp/ec6108v9"
sys.path.insert(0, str(BSP))
from sparse import inspect
from usb_disk import contents

PACKAGE = "armbian-kernel-ec6108v9"


def build(image, version, output):
    if not re.fullmatch(r"1\.[1-9][0-9]*\.[1-9][0-9]*", version):
        raise ValueError("Expected an APT workflow version")
    subprocess.run([sys.executable, str(PROJECT / "tools/verify-usb.py"), str(image)], check=True)
    output.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(prefix="ec6108-apt-") as temporary, contents(image) as files:
        scratch = Path(temporary)
        package = scratch / "package"
        payload = package / "usr/lib/ec6108v9/kernel"
        control = package / "DEBIAN"
        payload.mkdir(parents=True)
        control.mkdir()
        info = json.loads((files / "manifest.json").read_text())
        release = info["kernel_release"]
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,62}", release):
            raise ValueError("Unsupported kernel release")
        (payload / "kernel.json").write_text(json.dumps({
            key: info[key] for key in ("kernel_release", "kernel_sha256", "kernel_bytes")
        }, indent=2) + "\n")
        with (files / "mv100/kernel.bin").open("rb") as stream:
            (payload / "uImage").write_bytes(stream.read(info["kernel_bytes"]))
        shutil.copyfile(PROJECT / "config/boards/ec6108v9.json", payload / "board.json")
        shutil.copyfile(BSP / "install-kernel.py", payload / "install-kernel.py")
        shutil.copyfile(PROJECT / "tools/uimage.py", payload / "uimage.py")

        block_image = scratch / "root.ext4"
        with (files / "mv100/rootfs.ext4").open("rb") as packed, block_image.open("wb") as expanded:
            if inspect(packed, expanded) != info["rootfs"]:
                raise ValueError("Root filesystem hash differs")
        extract = subprocess.run(
            ["debugfs", "-R", f"rdump /usr/lib/modules/{release} {payload}", str(block_image)],
            check=True, capture_output=True, text=True)
        errors = [line for line in extract.stderr.splitlines()
                  if not (line.startswith("debugfs ") or
                          "Operation not permitted while changing ownership" in line)]
        if errors:
            raise ValueError("Module extraction failed: " + "\n".join(errors))
        modules = payload / "modules"
        (payload / release).rename(modules)
        for path in modules.rglob("*"):
            if path.is_symlink():
                path.unlink()
        if not any((modules / "kernel").rglob("*.ko*")):
            raise ValueError("Kernel modules missing from image")
        for path in [package, *package.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        license_dir = package / "usr/share/doc" / PACKAGE
        license_dir.mkdir(parents=True)
        shutil.copyfile(PROJECT / "LICENSE", license_dir / "copyright")
        (control / "control").write_text(
            f"Package: {PACKAGE}\nVersion: {version}\nArchitecture: {BOARD['debian_architecture']}\n"
            "Maintainer: EC6108V9 Armbian <chaeoi@users.noreply.github.com>\n"
            "Section: kernel\nPriority: optional\nDepends: python3 (>= 3.10), kmod, util-linux\n"
            "Description: Armbian kernel and boot image for the Huawei EC6108V9\n"
            " Installs the board kernel into the dedicated eMMC kernel partition.\n")
        postinst = control / "postinst"
        postinst.write_text(
            '#!/bin/sh\nset -eu\nif [ "$1" = configure ]; then\n'
            '    /usr/bin/python3 -B /usr/lib/ec6108v9/kernel/install-kernel.py\nfi\n')
        postinst.chmod(0o755)
        deb = output / f"{PACKAGE}_{version}_{BOARD['debian_architecture']}.deb"
        env = {**os.environ, "SOURCE_DATE_EPOCH": str(info["build"]["source"]["source_date_epoch"])}
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(package), str(deb)], env=env, check=True)
        return deb


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.image, args.version, args.output)
