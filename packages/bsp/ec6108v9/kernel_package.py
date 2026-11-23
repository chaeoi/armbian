#!/usr/bin/env python3
"""Build the board kernel payload shared by the USB installer and APT."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import uimage

PACKAGE = "armbian-kernel-ec6108v9"
PAYLOAD = Path("usr/lib/ec6108v9/kernel")


def kernel_abi(release):
    match = re.search(r"-ec6108v9\.([1-9][0-9]{0,5})-edge-hi3798mv100$", release)
    return int(match[1]) if match else 0


def image_package_version(metadata):
    abi = kernel_abi(metadata["kernel_release"])
    prefix = f"2.{abi}.0" if abi else "1.0.0"
    return f"{prefix}+{metadata['kernel_sha256'][:12]}"


def assemble(root, board, timestamp):
    root = root.resolve()
    if root == Path("/") or not (root / "etc/armbian-release").is_file():
        raise ValueError("Expected a separate Armbian image filesystem")
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
    for alias, expected in (("mmc0", "/soc@f0000000/ahb/mmc@9830000"),
                            ("mmc1", "/soc@f0000000/ahb/mmc@9820000")):
        actual = subprocess.check_output(["fdtget", str(dtb), "/aliases", alias], text=True).strip()
        if actual != expected:
            raise ValueError("Compiled DTB has an unsafe storage alias: " + alias)
    image = uimage.make_image(kernel.read_bytes(), dtb.read_bytes(), release, timestamp,
                              board["kernel_load_address"], board["kernel_read_bytes"])
    metadata = {"kernel_release": release, "kernel_bytes": len(image),
                "kernel_sha256": hashlib.sha256(image).hexdigest()}
    return image, metadata, modules[0]


def build_package(source, image, metadata, modules, version, output):
    board_file = source / "config/boards/ec6108v9.json"
    board = json.loads(board_file.read_text())
    uimage.validate_image(image, board["kernel_read_bytes"])
    if (not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,62}", metadata["kernel_release"])
            or metadata["kernel_bytes"] != len(image)
            or metadata["kernel_sha256"] != hashlib.sha256(image).hexdigest()):
        raise ValueError("Kernel package metadata differs from its image")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ec6108-deb-") as temporary:
        package = Path(temporary)
        payload = package / PAYLOAD
        control = package / "DEBIAN"
        payload.mkdir(parents=True)
        control.mkdir()
        (payload / "kernel.json").write_text(json.dumps(metadata, indent=2) + "\n")
        (payload / "uImage").write_bytes(image)
        shutil.copyfile(board_file, payload / "board.json")
        bsp = source / "packages/bsp/ec6108v9"
        shutil.copyfile(bsp / "install-kernel.py", payload / "install-kernel.py")
        shutil.copyfile(uimage.__file__, payload / "uimage.py")
        copied = payload / "modules"
        shutil.copytree(modules, copied, symlinks=True)
        for path in copied.rglob("*"):
            if path.is_symlink():
                path.unlink()
        if not any((copied / "kernel").rglob("*.ko*")):
            raise ValueError("Kernel modules missing from image")
        for path in [package, *package.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        license_dir = package / "usr/share/doc" / PACKAGE
        license_dir.mkdir(parents=True)
        shutil.copyfile(source / "LICENSE", license_dir / "copyright")
        (control / "control").write_text(
            f"Package: {PACKAGE}\nVersion: {version}\nArchitecture: {board['debian_architecture']}\n"
            "Maintainer: EC6108V9 Armbian <chaeoi@users.noreply.github.com>\n"
            "Section: kernel\nPriority: optional\nDepends: python3 (>= 3.10), kmod, util-linux\n"
            "Description: Armbian kernel and boot image for the Huawei EC6108V9\n"
            " Installs the board kernel into the dedicated eMMC kernel partition.\n")
        postinst = control / "postinst"
        postinst.write_text(
            '#!/bin/sh\nset -eu\nif [ "$1" = configure ] && [ "${EC6108V9_IMAGE_BUILD:-}" != 1 ]; then\n'
            '    /usr/bin/python3 -B /usr/lib/ec6108v9/kernel/install-kernel.py\nfi\n')
        postinst.chmod(0o755)
        info = json.loads((source / "config/sources/linux-hi3798mv100.json").read_text())
        env = {**os.environ, "SOURCE_DATE_EPOCH": str(info["source_date_epoch"])}
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(package), str(output)], env=env, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("root", "source", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    board = json.loads((args.source / "config/boards/ec6108v9.json").read_text())
    info = json.loads((args.source / "config/sources/linux-hi3798mv100.json").read_text())
    image, metadata, modules = assemble(args.root, board, info["source_date_epoch"])
    build_package(args.source, image, metadata, modules, image_package_version(metadata), args.output)
