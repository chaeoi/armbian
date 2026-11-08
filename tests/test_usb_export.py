# SPDX-License-Identifier: GPL-2.0-only
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
BSP = PROJECT / "packages/bsp/ec6108v9"
sys.path[:0] = [str(BSP), str(PROJECT / "tools")]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(all(shutil.which(name) for name in ("dtc", "fdtget", "mkfs.ext4")),
                     "Install device-tree-compiler and e2fsprogs for the ext4 export fixture")
class USBExportTests(unittest.TestCase):
    def test_prepare_export_and_verify_without_device_credentials(self):
        prepare = load("prepare_image", BSP / "prepare-image.py")
        exporter = load("build_usb", BSP / "build-usb.py")
        verifier = load("verify_usb", PROJECT / "tools/verify-usb.py")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, staging, output = [base / name for name in ("root", "staging", "output")]
            release = "fixture-kernel"
            for directory in ("etc/ssh", "root/.ssh", "boot/dtb-" + release + "/hisilicon",
                              "lib/modules/" + release, "var/lib/dbus"):
                (root / directory).mkdir(parents=True)
            (root / "etc/armbian-release").write_text("BOARD=ec6108v9\n")
            (root / "etc/ssh/ssh_host_ed25519_key").write_text("fixture identity, must be removed")
            (root / "root/.ssh/authorized_keys").write_text("fixture login, must be removed")
            (root / "etc/machine-id").write_text("fixture-machine")
            (root / "var/lib/dbus/machine-id").write_text("fixture-machine")
            kernel = bytearray(64)
            struct.pack_into("<I", kernel, 36, 0x016F2818)
            (root / "boot" / ("vmlinuz-" + release)).write_bytes(kernel)
            dts = base / "fixture.dts"
            dts.write_text('/dts-v1/; / { aliases { mmc0="/soc@f0000000/ahb/mmc@9830000"; '
                           'mmc1="/soc@f0000000/ahb/mmc@9820000"; }; };')
            dtb = root / "boot" / ("dtb-" + release) / "hisilicon/hi3798mv100-ec6108v9.dtb"
            subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(dtb), str(dts)], check=True)
            version = "Armbian-test_Ec6108v9_jammy_edge_fixture_minimal"
            prepare.prepare(root, staging, PROJECT, version)
            self.assertFalse((root / "etc/ssh/ssh_host_ed25519_key").exists())
            self.assertFalse((root / "root/.ssh").exists())
            self.assertEqual((root / "etc/machine-id").read_bytes(), b"")
            self.assertIn("/dev/mmcblk0p3", (root / "etc/fstab").read_text())
            filesystem = base / "rootfs.ext4"
            with filesystem.open("wb") as stream:
                stream.truncate(64 * 1024 * 1024)
            subprocess.run(["mkfs.ext4", "-q", "-F", "-d", str(root), str(filesystem)], check=True,
                           capture_output=True)
            image = base / "fixture.img"
            with image.open("wb") as target, filesystem.open("rb") as source:
                target.seek(34 * 1024 * 1024)
                shutil.copyfileobj(source, target)
            archive = exporter.export(image, staging, output, version, PROJECT)
            manifest = verifier.verify(archive)
            self.assertFalse(manifest["tested_boot"])
            self.assertFalse(manifest["private_device_configuration"])
            self.assertEqual(manifest["rootfs"]["expanded_bytes"], 64 * 1024 * 1024)
            self.assertTrue(archive.with_name(archive.name + ".sha256").exists())
            with zipfile.ZipFile(archive, "a") as package:
                package.writestr("management-key", "unexpected fixture key")
            with self.assertRaisesRegex(ValueError, "payload set"):
                verifier.verify(archive)


if __name__ == "__main__":
    unittest.main()
