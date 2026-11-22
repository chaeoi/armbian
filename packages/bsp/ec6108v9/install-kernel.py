#!/usr/bin/python3
"""Commit a board kernel to the EC6108V9's single eMMC kernel partition."""
# SPDX-License-Identifier: GPL-2.0-only
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

from uimage import validate_image

PAYLOAD = Path("/usr/lib/ec6108v9/kernel")
TARGET = Path("/dev/mmcblk0p2")
CONFIG = Path("/etc/ec6108-system.json")


def run(*arguments):
    return subprocess.check_output(arguments, text=True).strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_board(board, state):
    hardware = Path("/sys/class/block/mmcblk0")
    layout = board["layout"]
    compatible = Path("/proc/device-tree/compatible").read_bytes().split(b"\0")
    require(b"hisilicon,hi3798mv100" in compatible and b"hisilicon,hi3798mv100-ec6108v9" in compatible,
            "Expected the EC6108V9 device tree")
    require(state["installation"] == "single-armbian-direct-emmc"
            and Path("/").stat().st_dev == Path(layout["root_partition"]).stat().st_rdev,
            "Expected the installed eMMC root")
    require((hardware / "device/type").read_text().strip() == "MMC"
            and (hardware / "device/cid").read_text().strip() == state["emmc_cid"]
            and int((hardware / "size").read_text()) * 512 == board["emmc_bytes"],
            "eMMC identity or capacity differs")
    for partition, offset, length in (
        ("mmcblk0p2", layout["kernel_offset"], layout["kernel_partition_bytes"]),
        ("mmcblk0p3", layout["root_offset"], board["emmc_bytes"] - layout["root_offset"]),
    ):
        sysfs = hardware / partition
        require(int((sysfs / "start").read_text()) * 512 == offset
                and int((sysfs / "size").read_text()) * 512 == length, "eMMC partition layout differs")
    require(run("blkid", "-s", "UUID", "-o", "value", layout["root_partition"]) == state["root_uuid"],
            "Root UUID differs")
    with open("/dev/mmcblk0", "rb") as emmc:
        emmc.seek(layout["environment_offset"])
        require(digest(emmc.read(1024 * 1024)) == state["environment_sha256"],
                "Boot environment differs")
    require(stat.S_ISBLK(TARGET.stat().st_mode) and not run("lsblk", "-n", "-o", "MOUNTPOINTS", str(TARGET)),
            "Expected an unmounted kernel partition")


def prepare_modules(release):
    source = PAYLOAD / "modules"
    target = Path("/lib/modules") / release
    modules = sorted(path.relative_to(source) for path in (source / "kernel").rglob("*.ko*") if path.is_file())
    require(bool(modules), "Kernel module payload is empty")
    if target.exists():
        installed = sorted(path.relative_to(target) for path in (target / "kernel").rglob("*.ko*") if path.is_file())
        require(installed == modules and all((source / path).read_bytes() == (target / path).read_bytes()
                                             for path in modules), "Module ABI is already in use")
    else:
        with tempfile.TemporaryDirectory(prefix=".ec6108v9-", dir=target.parent) as staging:
            temporary = Path(staging) / release
            shutil.copytree(source, temporary)
            os.replace(temporary, target)
    subprocess.run(["depmod", "-a", release], check=True)


def write_partition(device, data):
    device.seek(0)
    require(device.write(data) == len(data), "Short eMMC write")
    os.fsync(device.fileno())
    os.posix_fadvise(device.fileno(), 0, len(data), os.POSIX_FADV_DONTNEED)
    device.seek(0)
    require(device.read(len(data)) == data, "eMMC readback differs")


def update(check_only):
    board = json.loads((PAYLOAD / "board.json").read_text())
    release = json.loads((PAYLOAD / "kernel.json").read_text())
    image = (PAYLOAD / "uImage").read_bytes()
    state = json.loads(CONFIG.read_text())
    fields = validate_image(image, board["kernel_read_bytes"])
    require(fields[5] == fields[4] == board["kernel_load_address"], "Unexpected boot address")
    name = release["kernel_release"]
    require(re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,62}", name) and
            release["kernel_bytes"] == len(image) and release["kernel_sha256"] == digest(image),
            "Kernel payload and metadata differ")
    check_board(board, state)
    size = board["layout"]["kernel_partition_bytes"]
    candidate = image.ljust(size, b"\0")
    flags = os.O_RDONLY if check_only else os.O_RDWR
    with os.fdopen(os.open(TARGET, flags | os.O_EXCL), "rb" if check_only else "r+b", buffering=0) as device:
        previous = device.read(size)
        require(len(previous) == size, "Short kernel partition read")
        old_size = state["kernel_bytes"]
        expected = (digest(previous[:old_size]) == state["kernel_sha256"] and not any(previous[old_size:]))
        require(expected or previous == candidate, "Current kernel partition differs from the installed record")
        require(name != os.uname().release or previous == candidate,
                "Different kernel images require different ABI names")
        if check_only:
            return
        prepare_modules(name)
        new_state = {**state, **{key: release[key] for key in ("kernel_release", "kernel_bytes", "kernel_sha256")}}
        if previous == candidate and new_state == state:
            print(f"EC6108V9 kernel verified on eMMC: {name}", flush=True)
            return
        with tempfile.NamedTemporaryFile(mode="w", dir=CONFIG.parent, prefix=".ec6108-kernel-",
                                         delete=False) as draft:
            pending = Path(draft.name)
            json.dump(new_state, draft, indent=2)
            draft.write("\n")
            draft.flush()
            os.fsync(draft.fileno())
        try:
            if previous != candidate:
                write_partition(device, candidate)
            os.replace(pending, CONFIG)
        except Exception:
            if previous != candidate:
                write_partition(device, previous)
            raise
        finally:
            pending.unlink(missing_ok=True)
    print(f"EC6108V9 kernel verified on eMMC: {name}", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with open("/run/ec6108v9-kernel.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        update(args.check)
