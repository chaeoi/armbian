#!/usr/bin/env python3
"""Package zImage + appended board DTB for the existing EC6108V9 bootloader."""
# SPDX-License-Identifier: GPL-2.0-only
import json
import os
from pathlib import Path
import shutil
import subprocess

from port import BOARD, BUILD, OUTPUT, PROJECT, SOURCE, SOURCE_INFO, sha256
from uimage import make_image, validate_image


def main():
    version = (BUILD / "include/config/kernel.release").read_text().strip()
    if version != SOURCE_INFO["kernel_release"]:
        raise RuntimeError("Unexpected kernel release: " + version)
    kernel = (BUILD / "arch/arm/boot/zImage").read_bytes()
    dtb_path = BUILD / "arch/arm/boot/dts" / BOARD["dtb_target"]
    dtb = dtb_path.read_bytes()
    compiled_tree = subprocess.run(
        [str(BUILD / "scripts/dtc/dtc"), "-I", "dtb", "-O", "dts", str(dtb_path)],
        check=True, capture_output=True, text=True).stdout
    for expected in ('mmc0 = "/soc@f0000000/ahb/mmc@9830000";',
                     'mmc1 = "/soc@f0000000/ahb/mmc@9820000";'):
        if expected not in compiled_tree:
            raise RuntimeError("Compiled DTB lacks the fixed eMMC/SD aliases")
    source_board = SOURCE / "arch/arm/boot/dts" / Path(BOARD["dtb_target"]).with_suffix(".dts")
    if source_board.read_bytes() != (PROJECT / BOARD["dts"]).read_bytes():
        raise RuntimeError("Board DTS changed; rebuild the kernel first")
    timestamp = int(os.environ.get("SOURCE_DATE_EPOCH", SOURCE_INFO["source_date_epoch"]))
    image = make_image(kernel, dtb, version, timestamp, BOARD["kernel_load_address"],
                       BOARD["kernel_read_bytes"])
    validate_image(image, BOARD["kernel_read_bytes"])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / "uImage-ec6108v9"
    destination.write_bytes(image)
    shutil.copy2(BUILD / ".config", OUTPUT / "kernel.config")
    shutil.copy2(dtb_path, OUTPUT / "hi3798mv100-ec6108v9.dtb")
    metadata = {
        "kernel_release": version, "image_bytes": len(image),
        "zimage_bytes": len(kernel), "dtb_bytes": len(dtb),
        "sha256": sha256(destination), "source": SOURCE_INFO,
        "source_patches": json.loads((PROJECT / BOARD["patch_series"]).read_text()),
        "board_dts_sha256": sha256(PROJECT / BOARD["dts"]),
        "kernel_config_sha256": sha256(OUTPUT / "kernel.config"),
        "compile_header": (BUILD / "include/generated/compile.h").read_text(),
        "source_date_epoch": timestamp,
        "tested_boot": False,
    }
    (OUTPUT / "kernel-manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
