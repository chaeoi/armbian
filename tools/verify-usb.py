#!/usr/bin/env python3
"""Validate an EC6108V9 USB installer disk without connecting to a device."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zlib

from port import BOARD, PROJECT
from uimage import validate_image

sys.path.insert(0, str(PROJECT / "packages/bsp/ec6108v9"))
from sparse import inspect
from usb_disk import contents, DISK_LAYOUT
from usb_layout import boot_environment, flash_environment, flash_positions


def verify(path):
    checksum = path.with_name(path.name + ".sha")
    if checksum.exists() or path.name.endswith(".img.xz"):
        fields = checksum.read_text().split()
        sha = hashlib.sha256()
        with path.open("rb") as stream:
            while data := stream.read(1024 * 1024):
                sha.update(data)
        if len(fields) != 2 or fields[1].lstrip("*") != path.name or sha.hexdigest() != fields[0]:
            raise ValueError("USB disk image checksum differs")
    with contents(path) as package:
        manifest = json.loads((package / "manifest.json").read_text())
        if (manifest["image_type"] != "usb-installer" or manifest["profile"] != "mdmo1d"
                or manifest["board"] != "ec6108v9" or manifest["emmc_bytes"] != BOARD["emmc_bytes"]
                or manifest["disk"] != DISK_LAYOUT):
            raise ValueError("Unexpected board image")
        positions = flash_positions(BOARD)
        if set(manifest["files"]) != set(positions):
            raise ValueError("Unexpected flashing file set")
        for key, (filename, sector, sectors) in positions.items():
            item = manifest["files"][key]
            if (item["filename"] != "mv100/" + filename or item["sector"] != sector
                    or item["sectors"] != sectors or item["sparse"] != (key == "root")):
                raise ValueError("USB flashing geometry differs")
        expected = {"fastboot.bin", "bootargs.bin", "manifest.json", "README.txt", "SHA256SUMS"}
        expected.update(item["filename"] for item in manifest["files"].values())
        actual = {item.relative_to(package).as_posix() for item in package.rglob("*") if item.is_file()}
        directories = {item.relative_to(package).as_posix() for item in package.rglob("*") if item.is_dir()}
        if actual != expected or directories != {"mv100"}:
            raise ValueError("Unexpected USB payload set")
        checksums = dict(line.split("  ", 1)[::-1] for line in (package / "SHA256SUMS").read_text().splitlines())
        if set(checksums) != expected - {"SHA256SUMS"}:
            raise ValueError("Incomplete checksum list")
        for name, checksum in checksums.items():
            digest = hashlib.sha256()
            with (package / name).open("rb") as stream:
                while data := stream.read(1024 * 1024):
                    digest.update(data)
            if digest.hexdigest() != checksum:
                raise ValueError("USB checksum mismatch: " + name)
        if (package / "bootargs.bin").read_bytes() != flash_environment(manifest["files"]):
            raise ValueError("USB flashing environment differs")
        if (package / "mv100/bootargs.bin").read_bytes() != boot_environment(BOARD):
            raise ValueError("Installed boot environment differs")
        loader = json.loads((PROJECT / "config/sources/usb-bootstrap.json").read_text())
        if hashlib.sha256((package / "fastboot.bin").read_bytes()).hexdigest() != loader["files"]["fastboot.bin"]["sha256"]:
            raise ValueError("BootROM loader differs")
        for item in manifest["files"].values():
            sha = hashlib.sha256()
            crc = 0
            file = package / item["filename"]
            if (file.stat().st_size != item["bytes"] or item["bytes"] <= 0
                    or (not item["sparse"] and item["bytes"] != item["sectors"] * 512)):
                raise ValueError("Bootloader payload size differs")
            with file.open("rb") as stream:
                while data := stream.read(1024 * 1024):
                    sha.update(data)
                    crc = zlib.crc32(data, crc)
            if sha.hexdigest() != item["sha256"] or crc != item["crc32"]:
                raise ValueError("Bootloader payload checksum differs")
            if item["sector"] < 0 or (item["sector"] + item["sectors"]) * 512 > BOARD["emmc_bytes"]:
                raise ValueError("Write exceeds eMMC bounds")
        kernel = (package / "mv100/kernel.bin").read_bytes()
        size = manifest["kernel_bytes"]
        validate_image(kernel[:size], BOARD["kernel_read_bytes"])
        if any(kernel[size:]):
            raise ValueError("Kernel partition padding is not zero")
        if hashlib.sha256(kernel[:size]).hexdigest() != manifest["kernel_sha256"]:
            raise ValueError("Kernel manifest digest differs")
        with (package / "mv100/rootfs.ext4").open("rb") as stream:
            rootfs = inspect(stream)
        if rootfs != manifest["rootfs"] or rootfs["expanded_bytes"] > positions["root"][2] * 512:
            raise ValueError("Sparse filesystem readback differs")
        sidecar = path.with_name(path.name.split(".img", 1)[0] + ".manifest.json")
        if sidecar.exists() and json.loads(sidecar.read_text()) != manifest:
            raise ValueError("Installer manifest sidecar differs")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    for image in parser.parse_args().images:
        metadata = verify(image)
        print(image.name + ": verified; " + metadata["kernel_release"] + "; hardware boot test pending")
