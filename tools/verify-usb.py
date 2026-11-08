#!/usr/bin/env python3
"""Validate an EC6108V9 USB ZIP without connecting to a device."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import zlib

from port import BOARD, PROJECT
from uimage import validate_image

sys.path.insert(0, str(PROJECT / "packages/bsp/ec6108v9"))
from sparse import inspect
from usb_layout import boot_environment, flash_environment


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise ValueError("Unsafe ZIP member")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["image_type"] != "usb-flash" or manifest["profile"] != "mdmo1d":
            raise ValueError("Unexpected board image")
        expected = {"fastboot.bin", "bootargs.bin", "manifest.json", "README.txt", "SHA256SUMS"}
        expected.update(item["filename"] for item in manifest["files"].values())
        if set(names) != expected:
            raise ValueError("Unexpected USB payload set")
        checksums = dict(line.split("  ", 1)[::-1] for line in archive.read("SHA256SUMS").decode().splitlines())
        if set(checksums) != expected - {"SHA256SUMS"}:
            raise ValueError("Incomplete checksum list")
        for name, checksum in checksums.items():
            digest = hashlib.sha256()
            with archive.open(name) as stream:
                while data := stream.read(1024 * 1024):
                    digest.update(data)
            if digest.hexdigest() != checksum:
                raise ValueError("USB checksum mismatch: " + name)
        if archive.read("bootargs.bin") != flash_environment(manifest["files"]):
            raise ValueError("USB flashing environment differs")
        if archive.read("mv100/bootargs.bin") != boot_environment(BOARD):
            raise ValueError("Installed boot environment differs")
        loader = json.loads((PROJECT / "config/sources/usb-bootstrap.json").read_text())
        if hashlib.sha256(archive.read("fastboot.bin")).hexdigest() != loader["files"]["fastboot.bin"]["sha256"]:
            raise ValueError("BootROM loader differs")
        for item in manifest["files"].values():
            sha = hashlib.sha256()
            crc = 0
            with archive.open(item["filename"]) as stream:
                while data := stream.read(1024 * 1024):
                    sha.update(data)
                    crc = zlib.crc32(data, crc)
            if sha.hexdigest() != item["sha256"] or crc != item["crc32"]:
                raise ValueError("Bootloader payload checksum differs")
            if item["sector"] < 0 or (item["sector"] + item["sectors"]) * 512 > BOARD["emmc_bytes"]:
                raise ValueError("Write exceeds eMMC bounds")
        kernel = archive.read("mv100/kernel.bin")
        size = manifest["kernel_bytes"]
        validate_image(kernel[:size], BOARD["kernel_read_bytes"])
        if any(kernel[size:]):
            raise ValueError("Kernel partition padding is not zero")
        if hashlib.sha256(kernel[:size]).hexdigest() != manifest["kernel_sha256"]:
            raise ValueError("Kernel manifest digest differs")
        with archive.open("mv100/rootfs.ext4") as stream:
            rootfs = inspect(stream)
        if rootfs != manifest["rootfs"]:
            raise ValueError("Sparse filesystem readback differs")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    for archive in parser.parse_args().archives:
        metadata = verify(archive)
        print(archive.name + ": verified; " + metadata["kernel_release"] + "; hardware boot test pending")
