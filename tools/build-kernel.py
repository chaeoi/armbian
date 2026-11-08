#!/usr/bin/env python3
"""Build the pinned EC6108V9 kernel using a standard ARM hard-float toolchain."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

from port import BOARD, BUILD, OUTPUT, PATCHES, PROJECT, SOURCE, SOURCE_INFO, sha256


def prepare_source():
    receipt = SOURCE / ".ec6108-source.json"
    if not receipt.is_file() or json.loads(receipt.read_text()) != SOURCE_INFO:
        raise RuntimeError("Run ./compile.sh fetch first, or select a fetched EC6108_SOURCE_DIR")
    for change in json.loads((PROJECT / BOARD["patch_series"]).read_text()):
        files = change.get("files", [change])

        def digest(item):
            path = SOURCE / item["file"]
            return sha256(path) if path.exists() else None

        if all(digest(item) == item["original_sha256"] for item in files):
            subprocess.run(["patch", "--batch", "--forward", "-d", str(SOURCE), "-p1",
                            "-i", str(PATCHES / change["patch"])], check=True)
        for item in files:
            if digest(item) != item["patched_sha256"]:
                raise RuntimeError("Unexpected source content: " + item["file"])
    board = PROJECT / BOARD["dts"]
    destination = SOURCE / "arch/arm/boot/dts" / Path(BOARD["dtb_target"]).with_suffix(".dts")
    if not destination.exists() or destination.read_bytes() != board.read_bytes():
        shutil.copyfile(board, destination)


def verify_configuration():
    def values(path):
        result = {}
        for line in path.read_text().splitlines():
            if line.startswith("CONFIG_") and "=" in line:
                key, value = line.split("=", 1)
                result[key] = value
            elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
                result[line[2:-11]] = "n"
        return result

    expected = values(PROJECT / BOARD["kernel_config"])
    actual = values(BUILD / ".config")
    for key, value in expected.items():
        if actual.get(key, "n") != value:
            raise RuntimeError(f"Kconfig changed {key}: expected {value}, got {actual.get(key, 'n')}")


def make_command():
    environment = os.environ.copy()
    prefix = environment.get("CROSS_COMPILE", "arm-linux-gnueabihf-")
    bundled = PROJECT / "work/build-tools"
    use_bundled = environment.get("EC6108_USE_BUNDLED_TOOLS") == "1"
    if use_bundled:
        environment["PATH"] = str(bundled / "usr/bin") + os.pathsep + environment["PATH"]
        environment["LD_LIBRARY_PATH"] = str(bundled / "usr/lib/x86_64-linux-gnu")
        environment["BISON_PKGDATADIR"] = str(bundled / "usr/share/bison")
        environment["M4"] = str(bundled / "usr/bin/m4")
        prefix = environment.get("CROSS_COMPILE", str(bundled / "usr/bin/arm-linux-gnueabihf-"))
    for name in ("make", "patch", "bison", "flex", prefix + "gcc"):
        if not shutil.which(name, path=environment["PATH"]):
            raise RuntimeError("Missing build dependency: " + name + "; see docs/BUILD.md")
    environment.setdefault("KBUILD_BUILD_USER", "ec6108v9-port")
    environment.setdefault("KBUILD_BUILD_HOST", "builder")
    environment.setdefault("KBUILD_BUILD_VERSION", "1")
    environment.setdefault("SOURCE_DATE_EPOCH", str(SOURCE_INFO["source_date_epoch"]))
    timestamp = datetime.fromtimestamp(int(environment["SOURCE_DATE_EPOCH"]), timezone.utc)
    environment.setdefault("KBUILD_BUILD_TIMESTAMP", timestamp.strftime("%a %b %d %H:%M:%S UTC %Y"))
    hostcc = environment.get("HOSTCC", "gcc")
    if use_bundled:
        compiler_dirs = sorted(path for base in
                               (bundled / "usr/libexec/gcc/x86_64-linux-gnu",
                                Path("/usr/libexec/gcc/x86_64-linux-gnu"))
                               for path in base.glob("*") if (path / "cc1").is_file())
        if compiler_dirs:
            hostcc += " -B" + str(compiler_dirs[-1]) + "/"
    command = ["make", "-C", str(SOURCE), "O=" + str(BUILD), "ARCH=arm",
               "CROSS_COMPILE=" + prefix, "HOSTCC=" + hostcc]
    if use_bundled:
        command += ["HOSTCFLAGS=-O2 -I" + str(bundled / "usr/include") + " -I" +
                    str(bundled / "usr/include/x86_64-linux-gnu"),
                    "HOSTLDFLAGS=-L" + str(bundled / "usr/lib/x86_64-linux-gnu")]
    return command, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "configure", "build", "modules", "modules-install"])
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("JOBS", "4")))
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    prepare_source()
    if args.mode == "prepare":
        print("Source patches and board DTS verified.")
        return
    command, environment = make_command()
    BUILD.mkdir(parents=True, exist_ok=True)

    def run(arguments):
        subprocess.run(command + arguments, env=environment, check=True)

    if args.mode == "configure":
        run([BOARD["kernel_defconfig"]])
        subprocess.run(["bash", str(SOURCE / "scripts/kconfig/merge_config.sh"), "-m", "-O",
                        str(BUILD), str(BUILD / ".config"), str(PROJECT / BOARD["kernel_config"])],
                       env=environment, check=True)
        run(["olddefconfig"])
        verify_configuration()
    else:
        verify_configuration()
        if args.mode == "build":
            run(["-j" + str(args.jobs), "zImage", BOARD["dtb_target"], "modules"])
        elif args.mode == "modules":
            run(["-j" + str(args.jobs), "modules"])
        else:
            run(["INSTALL_MOD_PATH=" + str(OUTPUT / "kernel-modules"), "modules_install"])


if __name__ == "__main__":
    main()
