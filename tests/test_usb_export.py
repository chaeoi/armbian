# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import importlib.util
import lzma
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
BSP = PROJECT / "packages/bsp/ec6108v9"
sys.path[:0] = [str(BSP), str(PROJECT / "tools")]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(all(shutil.which(name) for name in
                        ("dtc", "fdtget", "mkfs.ext4", "mkfs.fat", "fsck.fat", "mcopy", "mdir")),
                     "Install device-tree-compiler, e2fsprogs, dosfstools and mtools for the disk fixture")
class USBExportTests(unittest.TestCase):
    def test_prepare_export_and_verify_without_device_credentials(self):
        prepare = load("prepare_image", BSP / "prepare-image.py")
        exporter = load("build_usb", BSP / "build-usb.py")
        verifier = load("verify_usb", PROJECT / "tools/verify-usb.py")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, staging, output = [base / name for name in ("root", "staging", "output")]
            release = "fixture-kernel"
            for directory in ("etc/ssh", "root/.ssh", "boot/dtb-" + release,
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
            dtb = root / "boot" / ("dtb-" + release) / "hi3798mv100-ec6108v9.dtb"
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
            output.mkdir()
            image = output / (version + ".img")
            with image.open("wb") as target, filesystem.open("rb") as source:
                target.seek(34 * 1024 * 1024)
                shutil.copyfileobj(source, target)
            disk = exporter.export(image, staging, output, version, PROJECT)
            self.assertEqual(disk, image)
            self.assertEqual(disk.stat().st_size, 512 * 1024 * 1024)
            manifest = verifier.verify(disk)
            self.assertFalse(manifest["tested_boot"])
            self.assertFalse(manifest["private_device_configuration"])
            self.assertEqual(manifest["rootfs"]["expanded_bytes"], 64 * 1024 * 1024)
            self.assertEqual(manifest["image_type"], "usb-installer")
            compressed = disk.with_name(disk.name + ".xz")
            with disk.open("rb") as source, lzma.open(compressed, "wb", preset=0) as target:
                shutil.copyfileobj(source, target)
            checksum = compressed.with_name(compressed.name + ".sha")
            sha = hashlib.sha256(compressed.read_bytes()).hexdigest()
            checksum.write_text(sha + "  " + compressed.name + "\n")
            self.assertEqual(verifier.verify(compressed), manifest)
            checksum.write_text("0" * 64 + "  " + compressed.name + "\n")
            with self.assertRaisesRegex(ValueError, "image checksum"):
                verifier.verify(compressed)
            with disk.open("r+b") as stream:
                stream.seek(446 + 8)
                stream.write(struct.pack("<I", 4096))
            with self.assertRaisesRegex(ValueError, "partition table"):
                verifier.verify(disk)
            with disk.open("r+b") as stream:
                stream.seek(446 + 8)
                stream.write(struct.pack("<I", 2048))
            private = base / "management-key"
            private.write_text("unexpected fixture key")
            subprocess.run(["mcopy", "-i", str(disk) + "@@1048576", str(private), "::/"], check=True)
            with self.assertRaisesRegex(ValueError, "payload set"):
                verifier.verify(disk)


if __name__ == "__main__":
    unittest.main()
