#!/usr/bin/env python3
"""Check the actual configuration resolved by the official Armbian framework."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import json
from pathlib import Path

from port import SOURCE_INFO


def verify(path):
    values = json.loads(path.read_text())
    expected = {"ARCH": "armhf", "BOARD_TYPE": "tvb", "BOARDFAMILY": "hi3798mv100",
                "BOARD_NAME": "Huawei EC6108V9", "BOOTCONFIG": "none", "ROOTFS_TYPE": "ext4",
                "KERNELSOURCE": SOURCE_INFO["repository"], "KERNELBRANCH": "commit:" + SOURCE_INFO["commit"],
                "KERNELPATCHDIR": "archive/hi3798mv100-7.3", "OFFSET": "34", "EXTRAWIFI": "no",
                "SKIP_COMPRESSING": "json"}
    for name, expected_value in expected.items():
        if values.get(name) != expected_value:
            raise ValueError("Unexpected framework setting: " + name)
    artifacts = values["WANT_ARTIFACT_ALL_NAMES_ARRAY"]
    if not {"kernel", "armbian-bsp-cli", "rootfs"}.issubset(artifacts):
        raise ValueError("Official kernel/BSP/rootfs pipeline is incomplete")
    if "uboot" in artifacts or "firmware" in artifacts or "full_firmware" in artifacts:
        raise ValueError("Unexpected generic bootloader or full firmware artifact")
    print("Official framework resolved EC6108V9 TV box, pinned kernel, BSP and rootfs correctly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", type=Path)
    verify(parser.parse_args().configuration)
