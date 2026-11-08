"""Android sparse images for the HiSTB U-Boot ext4 writer."""
# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import struct

MAGIC = 0xED26FF3A
RAW, FILL, SKIP = 0xCAC1, 0xCAC2, 0xCAC3
HEADER = struct.Struct("<I4H4I")
CHUNK = struct.Struct("<2H2I")
BLOCK = 4096


def encode(source, destination):
    """Encode zero runs as FILL, so old flash contents cannot replace zero blocks."""
    zero = bytes(BLOCK)
    raw = bytearray()
    zeros = chunks = blocks = 0
    destination.write(bytes(HEADER.size))

    def flush_raw():
        nonlocal chunks
        if raw:
            destination.write(CHUNK.pack(RAW, 0, len(raw) // BLOCK, CHUNK.size + len(raw)))
            destination.write(raw)
            raw.clear()
            chunks += 1

    def flush_zero():
        nonlocal zeros, chunks
        if zeros:
            destination.write(CHUNK.pack(FILL, 0, zeros, CHUNK.size + 4))
            destination.write(bytes(4))
            zeros = 0
            chunks += 1

    while data := source.read(BLOCK):
        if len(data) != BLOCK:
            raise ValueError("Raw filesystem size must be a multiple of 4096")
        blocks += 1
        if data == zero:
            flush_raw()
            zeros += 1
        else:
            flush_zero()
            raw.extend(data)
            if len(raw) >= 1024 * 1024:
                flush_raw()
    flush_raw()
    flush_zero()
    if not blocks:
        raise ValueError("Empty root filesystem")
    destination.seek(0)
    destination.write(HEADER.pack(MAGIC, 1, 0, HEADER.size, CHUNK.size, BLOCK, blocks, chunks, 0))
    destination.seek(0, 2)
    return blocks * BLOCK


def inspect(source):
    header = source.read(HEADER.size)
    if len(header) != HEADER.size:
        raise ValueError("Truncated sparse header")
    magic, major, minor, file_size, chunk_size, block_size, blocks, count, checksum = HEADER.unpack(header)
    if (magic, major, minor, file_size, chunk_size, block_size) != (MAGIC, 1, 0, HEADER.size, CHUNK.size, BLOCK):
        raise ValueError("Unsupported sparse image header")
    digest = hashlib.sha256()
    total = 0
    for _ in range(count):
        data = source.read(CHUNK.size)
        if len(data) != CHUNK.size:
            raise ValueError("Truncated sparse chunk")
        kind, reserved, chunk_blocks, length = CHUNK.unpack(data)
        if not chunk_blocks:
            raise ValueError("Empty sparse chunk")
        if kind == RAW:
            if length != CHUNK.size + chunk_blocks * BLOCK:
                raise ValueError("Invalid RAW chunk length")
            remaining = chunk_blocks * BLOCK
            while remaining:
                data = source.read(min(remaining, 1024 * 1024))
                if not data:
                    raise ValueError("Truncated RAW chunk")
                digest.update(data)
                remaining -= len(data)
        elif kind == FILL:
            if length != CHUNK.size + 4:
                raise ValueError("Invalid FILL chunk length")
            value = source.read(4)
            if len(value) != 4:
                raise ValueError("Truncated FILL chunk")
            data = value * (BLOCK // 4)
            for _ in range(chunk_blocks):
                digest.update(data)
        else:
            raise ValueError("Only explicit RAW/FILL chunks are allowed")
        total += chunk_blocks
    if total != blocks or source.read(1):
        raise ValueError("Sparse size mismatch or trailing data")
    return {"expanded_bytes": total * BLOCK, "expanded_sha256": digest.hexdigest(), "chunks": count}
