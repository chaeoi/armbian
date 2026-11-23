#!/usr/bin/env python3
"""Package the EC6108V9 kernel and modules from a verified USB image."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from port import BOARD, PROJECT

BSP = PROJECT / "packages/bsp/ec6108v9"
sys.path.insert(0, str(BSP))
from kernel_package import PACKAGE, build_package, kernel_abi
from sparse import inspect
from usb_disk import contents


def build(image, version, output, require_abi=False):
    if not re.fullmatch(r"1\.[1-9][0-9]*\.[1-9][0-9]*", version):
        raise ValueError("Expected an APT workflow version")
    subprocess.run([sys.executable, str(PROJECT / "tools/verify-usb.py"), str(image)], check=True)
    output.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(prefix="ec6108-apt-") as temporary, contents(image) as files:
        scratch = Path(temporary)
        info = json.loads((files / "manifest.json").read_text())
        release = info["kernel_release"]
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,62}", release):
            raise ValueError("Unsupported kernel release")
        if require_abi:
            abi = kernel_abi(release)
            if not abi:
                raise ValueError("Published APT kernels must have an explicit EC6108V9 ABI")
            version = f"2.{abi}.{version.removeprefix('1.')}"
        metadata = {key: info[key] for key in ("kernel_release", "kernel_sha256", "kernel_bytes")}
        with (files / "mv100/kernel.bin").open("rb") as stream:
            kernel = stream.read(info["kernel_bytes"])

        block_image = scratch / "root.ext4"
        with (files / "mv100/rootfs.ext4").open("rb") as packed, block_image.open("wb") as expanded:
            if inspect(packed, expanded) != info["rootfs"]:
                raise ValueError("Root filesystem hash differs")
        extract = subprocess.run(
            ["debugfs", "-R", f"rdump /usr/lib/modules/{release} {scratch}", str(block_image)],
            check=True, capture_output=True, text=True)
        errors = [line for line in extract.stderr.splitlines()
                  if not (line.startswith("debugfs ") or
                          "Operation not permitted while changing ownership" in line)]
        if errors:
            raise ValueError("Module extraction failed: " + "\n".join(errors))
        deb = output / f"{PACKAGE}_{version}_{BOARD['debian_architecture']}.deb"
        build_package(PROJECT, kernel, metadata, scratch / release, version, deb)
        return deb


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-abi", action="store_true")
    parser.add_argument("image", type=Path)
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.image, args.version, args.output, args.require_abi)
