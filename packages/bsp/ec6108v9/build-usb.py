#!/usr/bin/env python3
"""Export an official Armbian rootfs as a FAT32 Hi3798MV100 USB installer disk."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import uuid
import zlib

from sparse import encode, inspect
from usb_disk import create, DISK_LAYOUT
from usb_layout import boot_environment, flash_environment, flash_positions
from uimage import validate_image


def digest(path):
    sha = hashlib.sha256()
    crc = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
            crc = zlib.crc32(block, crc)
    return sha.hexdigest(), crc


def export(image, staging, output, version, source_root):
    board = json.loads((source_root / "config/boards/ec6108v9.json").read_text())
    bootstrap = json.loads((source_root / "config/sources/usb-bootstrap.json").read_text())
    metadata = json.loads((staging / "image.json").read_text())
    kernel = (staging / "uImage").read_bytes()
    validate_image(kernel, board["kernel_read_bytes"])
    for item in bootstrap["files"].values():
        if digest(source_root / item["path"])[0] != item["sha256"]:
            raise ValueError("Board boot asset digest mismatch")
    loader = (source_root / bootstrap["files"]["fastboot.bin"]["path"]).read_bytes()
    if bootstrap["reg_name"].encode() not in loader:
        raise ValueError("Bootloader REG profile differs")
    with image.open("rb") as stream:
        stream.seek(board["layout"]["root_offset"] + 1024)
        superblock = stream.read(1024)
    if len(superblock) != 1024 or superblock[56:58] != b"\x53\xef":
        raise ValueError("No ext4 root filesystem at the expected image offset")
    block_size = 1024 << struct.unpack_from("<I", superblock, 24)[0]
    blocks = struct.unpack_from("<I", superblock, 4)[0]
    if struct.unpack_from("<I", superblock, 96)[0] & 0x80:
        blocks |= struct.unpack_from("<I", superblock, 336)[0] << 32
    root_bytes = blocks * block_size
    if root_bytes <= 0 or root_bytes > board["emmc_bytes"] - board["layout"]["root_offset"]:
        raise ValueError("Root filesystem does not fit the target eMMC")
    if image.stat().st_size < board["layout"]["root_offset"] + root_bytes:
        raise ValueError("Truncated image")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ec6108-usb-", dir=output) as temporary:
        package = Path(temporary)
        payload = package / "mv100"
        payload.mkdir()
        (package / "fastboot.bin").write_bytes(loader)
        (payload / "bootargs.bin").write_bytes(boot_environment(board))

        class RootReader:
            def __init__(self, stream):
                self.stream, self.remaining = stream, root_bytes
                self.digest = hashlib.sha256()

            def read(self, size):
                data = self.stream.read(min(size, self.remaining)) if self.remaining else b""
                if self.remaining and not data:
                    raise ValueError("Truncated root filesystem")
                self.remaining -= len(data)
                self.digest.update(data)
                return data

        with image.open("rb") as source, (payload / "rootfs.ext4").open("w+b") as target:
            source.seek(board["layout"]["root_offset"])
            reader = RootReader(source)
            encode(reader, target)
            original_sha = reader.digest.hexdigest()
        if (payload / "rootfs.ext4").stat().st_size > bootstrap["max_rootfs_sparse_bytes"]:
            raise ValueError("Sparse rootfs exceeds the bootloader RAM buffer limit")
        with (payload / "rootfs.ext4").open("rb") as stream:
            sparse_info = inspect(stream)
        if sparse_info["expanded_bytes"] != root_bytes or sparse_info["expanded_sha256"] != original_sha:
            raise ValueError("Sparse rootfs readback differs")

        def padded(name, data, size):
            if len(data) > size:
                raise ValueError("Payload exceeds its partition: " + name)
            (payload / name).write_bytes(data + bytes(size - len(data)))

        padded("kernel.bin", kernel, board["layout"]["kernel_partition_bytes"])
        padded("fastboot.bin", loader, 1024 * 1024)
        for name in ("baseparam.img", "pq_param.bin", "logo.img"):
            padded(name, (source_root / bootstrap["files"][name]["path"]).read_bytes(), 4 * 1024 * 1024)
        files = {}
        for key, (name, sector, sectors) in flash_positions(board).items():
            sha, crc = digest(payload / name)
            files[key] = {"filename": "mv100/" + name, "sector": sector, "sectors": sectors,
                          "sha256": sha, "crc32": crc, "bytes": (payload / name).stat().st_size,
                          "sparse": key == "root"}
        (package / "bootargs.bin").write_bytes(flash_environment(files))
        manifest = {"release": version, "image_type": "usb-installer", "disk": DISK_LAYOUT,
                    "board": "ec6108v9",
                    "profile": "mdmo1d", "emmc_bytes": board["emmc_bytes"],
                    "kernel_release": metadata["kernel_release"], "kernel_bytes": len(kernel),
                    "kernel_sha256": hashlib.sha256(kernel).hexdigest(),
                    "root_uuid": str(uuid.UUID(bytes=superblock[104:120])),
                    "rootfs": sparse_info, "files": files,
                    "single_os": True, "fallback": False, "private_device_configuration": False,
                    "tested_boot": False, "usb_boot_hardware_tested": False,
                    "bootstrap": bootstrap, "build": metadata}
        (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (package / "README.txt").write_text(
            "EC6108V9 / Hi3798MV100 / mdmo1d / 1 GiB RAM / 4 GB eMMC only.\n"
            "Write the .img.xz image to a USB 2.0 drive using Armbian Imager (local/custom image).\n"
            "This FAT32 volume is an installer that writes Armbian to internal eMMC.\n"
            "Power off, connect USB and Ethernet, use the USB-boot short for the actual PCB, then power on.\n"
            "Release the short after USB boot starts. Wait for installation and the automatic reboot.\n"
            "This erases the internal OS. Keep power connected. Remove this USB drive after installation.\n"
            "SSH: root / 1234. Change the password at first login. No Wi-Fi credentials are included.\n"
            "This build has not been boot-tested. Check the repository validation report before flashing.\n")
        names = sorted(path for path in package.rglob("*") if path.is_file())
        (package / "SHA256SUMS").write_text("".join(digest(path)[0] + "  " + path.relative_to(package).as_posix() + "\n" for path in names))
        destination = output / (version + ".img")
        create(package, destination, version)
        (output / (version + ".manifest.json")).write_text(json.dumps(manifest, indent=2) + "\n")
        print(destination)
        return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("image", "staging", "output", "source-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if Path(args.version).name != args.version or not args.version.startswith("Armbian"):
        parser.error("Unexpected Armbian image version")
    export(args.image, args.staging, args.output, args.version, args.source_root)


if __name__ == "__main__":
    main()
