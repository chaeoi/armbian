"""Legacy ARM uImage serialization and validation; no device access."""
# SPDX-License-Identifier: GPL-2.0-only
import struct
import zlib

MAGIC = 0x27051956


def make_image(kernel, dtb, release, timestamp, address, limit):
    if len(kernel) < 40 or struct.unpack("<I", kernel[36:40])[0] != 0x016F2818:
        raise ValueError("Invalid ARM zImage magic")
    if len(dtb) < 40 or struct.unpack(">I", dtb[:4])[0] != 0xD00DFEED:
        raise ValueError("Invalid device tree magic")
    if struct.unpack(">I", dtb[4:8])[0] != len(dtb):
        raise ValueError("Device tree length mismatch")
    payload = kernel + dtb
    if 64 + len(payload) > limit:
        raise ValueError("Image exceeds the bootloader's fixed kernel read size")
    header = struct.pack(">7I4B32s", MAGIC, 0, timestamp, len(payload), address, address,
                         zlib.crc32(payload), 5, 2, 2, 0,
                         ("Linux-" + release).encode("ascii")[:32].ljust(32, b"\0"))
    return header[:4] + struct.pack(">I", zlib.crc32(header)) + header[8:] + payload


def validate_image(image, limit):
    if len(image) < 64 or len(image) > limit:
        raise ValueError("Invalid uImage length")
    fields = struct.unpack(">7I4B32s", image[:64])
    header = image[:4] + b"\0" * 4 + image[8:64]
    if fields[0] != MAGIC or zlib.crc32(header) != fields[1]:
        raise ValueError("Invalid uImage header or CRC")
    if fields[3] != len(image) - 64 or zlib.crc32(image[64:]) != fields[6]:
        raise ValueError("Invalid uImage payload or CRC")
    if fields[7:11] != (5, 2, 2, 0):
        raise ValueError("Expected Linux ARM kernel with no uImage compression")
    return fields
