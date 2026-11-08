"""Create and read a partitioned FAT32 USB installer without loop devices."""
# SPDX-License-Identifier: GPL-2.0-only
from contextlib import contextmanager
import hashlib
import lzma
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tempfile

SECTOR_BYTES = 512
DISK_BYTES = 512 * 1024 * 1024
START_SECTOR = 2048
PARTITION_SECTORS = DISK_BYTES // SECTOR_BYTES - START_SECTOR
DISK_LAYOUT = {"partition_table": "dos", "bytes": DISK_BYTES, "sector_bytes": SECTOR_BYTES,
               "partition_start_sector": START_SECTOR, "partition_sectors": PARTITION_SECTORS,
               "partition_type": 0x0C, "filesystem": "FAT32", "label": "ARMBIAN"}


def run(*arguments):
    result = subprocess.run(arguments, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(arguments[0] + " failed: " + (result.stdout + result.stderr).strip())
    return result.stdout


def mbr(version):
    data = bytearray(SECTOR_BYTES)
    data[440:444] = hashlib.sha256(version.encode()).digest()[:4]
    struct.pack_into("<B3sB3sII", data, 446, 0x80, b"\x20\x21\x00", 0x0C,
                     b"\xfe\xff\xff", START_SECTOR, PARTITION_SECTORS)
    data[510:512] = b"\x55\xaa"
    return data


def create(package, destination, version):
    """Replace the intermediate rootfs image only after building the installer."""
    with tempfile.TemporaryDirectory(prefix="ec6108-disk-", dir=destination.parent) as temporary:
        base = Path(temporary)
        filesystem = base / "installer.fat"
        with filesystem.open("wb") as stream:
            stream.truncate(PARTITION_SECTORS * SECTOR_BYTES)
        # Disable track rounding so the BPB spans the exact MBR partition.
        run("mkfs.fat", "--invariant", "-a", "-F", "32", "-S", "512", "-s", "8",
            "-g", "255/63", "-h", str(START_SECTOR), "-n", "ARMBIAN", str(filesystem))
        # Keep the BootROM loader first in the FAT root directory.
        for name in ("fastboot.bin", "bootargs.bin", "mv100", "manifest.json", "README.txt", "SHA256SUMS"):
            run("mcopy", "-s", "-i", str(filesystem), str(package / name), "::/")
        run("fsck.fat", "-n", str(filesystem))
        disk = base / "installer.img"
        with disk.open("wb") as target, filesystem.open("rb") as source:
            target.write(mbr(version))
            target.seek(START_SECTOR * SECTOR_BYTES)
            shutil.copyfileobj(source, target, 1024 * 1024)
        validate_layout(disk)
        disk.replace(destination)


def validate_layout(path):
    if path.stat().st_size != DISK_BYTES:
        raise ValueError("Unexpected USB disk image size")
    with path.open("rb") as stream:
        header = stream.read(SECTOR_BYTES)
        entry = struct.unpack_from("<B3sB3sII", header, 446)
        if (header[510:512] != b"\x55\xaa" or entry[0] != 0x80 or entry[2] != 0x0C
                or entry[4:] != (START_SECTOR, PARTITION_SECTORS) or any(header[462:510])):
            raise ValueError("Unexpected USB partition table")
        stream.seek(START_SECTOR * SECTOR_BYTES)
        boot = stream.read(SECTOR_BYTES)
    if (boot[510:512] != b"\x55\xaa" or boot[82:90] != b"FAT32   "
            or struct.unpack_from("<H", boot, 11)[0] != SECTOR_BYTES or boot[13] != 8
            or boot[16] != 2 or struct.unpack_from("<H", boot, 22)[0] != 0
            or struct.unpack_from("<I", boot, 28)[0] != START_SECTOR
            or struct.unpack_from("<I", boot, 32)[0] != PARTITION_SECTORS
            or boot[71:82] != b"ARMBIAN    "):
        raise ValueError("Unexpected USB FAT32 filesystem")


@contextmanager
def contents(path):
    """Read .img or .img.xz and expose only validated FAT file paths."""
    with tempfile.TemporaryDirectory(prefix="ec6108-verify-") as temporary:
        base = Path(temporary)
        image = path
        if path.name.endswith(".img.xz"):
            image = base / "installer.img"
            with lzma.open(path, "rb") as source, image.open("wb") as target:
                remaining = DISK_BYTES
                while remaining:
                    data = source.read(min(1024 * 1024, remaining))
                    if not data:
                        raise ValueError("Truncated compressed USB disk image")
                    target.write(data)
                    remaining -= len(data)
                if source.read(1):
                    raise ValueError("Oversized compressed USB disk image")
        elif not path.name.endswith(".img"):
            raise ValueError("Expected a USB .img or .img.xz disk image")
        validate_layout(image)
        filesystem = base / "installer.fat"
        with image.open("rb") as source, filesystem.open("wb") as target:
            source.seek(START_SECTOR * SECTOR_BYTES)
            shutil.copyfileobj(source, target, 1024 * 1024)
        run("fsck.fat", "-n", str(filesystem))
        listing = run("mdir", "-a", "-b", "-s", "-i", str(filesystem), "::/")
        directory = base / "files"
        directory.mkdir()
        seen = set()
        for line in listing.splitlines():
            if not line.startswith("::/"):
                raise ValueError("Unexpected FAT directory entry")
            name = line[3:]
            relative = PurePosixPath(name)
            if (not name or relative.is_absolute() or ".." in relative.parts
                    or "\\" in name or any(ord(character) < 32 for character in name)
                    or relative.as_posix().casefold() in seen):
                raise ValueError("Unsafe FAT directory entry")
            seen.add(relative.as_posix().casefold())
            target = directory / name
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                run("mcopy", "-i", str(filesystem), "::/" + name, str(target))
        yield directory
