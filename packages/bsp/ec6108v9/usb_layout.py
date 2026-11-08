"""Build both U-Boot environments for a standalone EC6108V9 USB installer."""
# SPDX-License-Identifier: GPL-2.0-only
from collections import OrderedDict
import struct
import zlib

ENV_SIZE = 65536
LOAD = "0x1000000"
SCRATCH, EXPECTED = "0x800000", "0x800004"


def environment(values):
    payload = b"\0".join(key.encode() + b"=" + value.encode() for key, value in values.items()) + b"\0\0"
    if len(payload) > ENV_SIZE - 4:
        raise ValueError("U-Boot environment is too large")
    payload = payload.ljust(ENV_SIZE - 4, b"\xff")
    return struct.pack("<I", zlib.crc32(payload)) + payload


def decode(data):
    if len(data) != ENV_SIZE or zlib.crc32(data[4:]) != struct.unpack("<I", data[:4])[0]:
        raise ValueError("Invalid U-Boot environment CRC")
    return OrderedDict(item.decode().split("=", 1) for item in data[4:].split(b"\0\0", 1)[0].split(b"\0"))


def boot_environment(board):
    layout = board["layout"]["blkdevparts"]
    arguments = ("console=ttyAMA0,115200 root=/dev/mmcblk0p3 rootfstype=ext4 rootwait rw "
                 "blkdevparts=" + layout + " mem=1G mmz=ddr,0,0,48M vmalloc=500M net.ifnames=0")
    if len("setenv bootargs " + arguments) >= 256:
        raise ValueError("Boot arguments exceed the board command limit")
    values = OrderedDict(baudrate="115200", bootdelay="2", stdin="serial", stdout="serial", stderr="serial",
                         ethaddr="00:11:22:33:44:55", bootargs=arguments,
                         bootcmd="mmc read 0 0x1FFFFC0 0x7000 0x4000; bootm 0x1FFFFC0")
    for memory in ("512M", "768M", "1G", "2G", "1536M", "3840M"):
        values["bootargs_" + memory] = arguments
    return environment(values)


def flash_environment(files):
    """Validate all files before writes. Commit normal boot settings last."""
    values = OrderedDict(baudrate="115200", bootdelay="0", stdin="serial", stdout="serial", stderr="serial",
                         bootargs="console=ttyAMA0,115200", ethaddr="00:11:22:33:44:55")
    for memory in ("512M", "768M", "1G", "2G"):
        values["bootargs_" + memory] = "mem=" + memory + " mmz=ddr,0,0,48M vmalloc=500M"
    for key, item in files.items():
        values["load_" + key] = "fatload usb 0 " + LOAD + " " + item["filename"]
        values["check_" + key] = ("crc32 " + LOAD + " ${filesize} " + SCRATCH +
                                 "; mw.l " + EXPECTED + " " + hex(item["crc32"]) +
                                 "; cmp.l " + SCRATCH + " " + EXPECTED + " 1")
        values["verify_" + key] = ("if run load_" + key + "; then run check_" + key + "; else false; fi")
        command = "mmc write.ext4sp" if item.get("sparse") else "mmc write"
        values["write_" + key] = (command + " 0 " + LOAD + " " + hex(item["sector"]) + " " + hex(item["sectors"]))
        values["flash_" + key] = ("if run verify_" + key + "; then run write_" + key + "; else false; fi")
    order = ("root", "kernel", "base", "pq", "logo", "loader", "bootargs")
    if set(files) != set(order):
        raise ValueError("Unexpected USB flashing file set")
    values["verify_all"] = "run " + " ".join("verify_" + key for key in order)
    values["flash_all"] = "run " + " ".join("flash_" + key for key in order)
    values["bootcmd"] = ("if run verify_all; then if run flash_all; then echo Armbian-installed; reset; "
                         "else echo Flash-failed-do-not-remove-USB; fi; else echo USB-file-check-failed; fi")
    for key, value in values.items():
        if len(value) >= 256:
            raise ValueError("U-Boot command exceeds the board limit: " + key)
    return environment(values)
