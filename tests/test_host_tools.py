# SPDX-License-Identifier: GPL-2.0-only
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from uimage import make_image, validate_image


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootImageTests(unittest.TestCase):
    def setUp(self):
        self.kernel = bytearray(64)
        struct.pack_into("<I", self.kernel, 36, 0x016F2818)
        self.dtb = struct.pack(">II", 0xD00DFEED, 40) + bytes(32)

    def image(self, limit=8192):
        return make_image(self.kernel, self.dtb, "test", 1234, 0x2000000, limit)

    def test_header_addresses_and_repeatability(self):
        image = self.image()
        fields = validate_image(image, 8192)
        self.assertEqual(fields[4:6], (0x2000000, 0x2000000))
        self.assertEqual(fields[3], len(self.kernel) + len(self.dtb))
        self.assertEqual(image, self.image())

    def test_corruption_and_truncation_are_rejected(self):
        original = self.image()
        for offset in (8, 64, len(original) - 1):
            damaged = bytearray(original)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                validate_image(damaged, 8192)
        with self.assertRaises(ValueError):
            validate_image(original[:-1], 8192)

    def test_actual_bootloader_limit_is_enforced(self):
        exact = 64 + len(self.kernel) + len(self.dtb)
        validate_image(self.image(exact), exact)
        with self.assertRaises(ValueError):
            self.image(exact - 1)

    def test_invalid_appended_device_tree_is_rejected(self):
        self.dtb = self.dtb[:-1]
        with self.assertRaisesRegex(ValueError, "device tree|Device tree"):
            self.image()


class BuildGuardsTests(unittest.TestCase):
    def test_configuration_does_not_silently_drop_nat_or_disabled_display(self):
        build = load("build_kernel", "build-kernel.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fragment = root / "fragment"
            fragment.write_text("CONFIG_NF_NAT=m\n# CONFIG_DRM is not set\n")
            config = root / ".config"
            with patch.object(build, "PROJECT", root), patch.object(build, "BUILD", root), \
                    patch.dict(build.BOARD, {"kernel_config": "fragment"}):
                config.write_text("CONFIG_NF_NAT=m\n# CONFIG_DRM is not set\n")
                build.verify_configuration()
                for text in ("# CONFIG_NF_NAT is not set\n", "CONFIG_NF_NAT=m\nCONFIG_DRM=y\n"):
                    config.write_text(text)
                    with self.assertRaises(RuntimeError):
                        build.verify_configuration()

    def test_unidentified_source_tree_is_not_patched(self):
        build = load("build_kernel", "build-kernel.py")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(build, "SOURCE", Path(directory)):
                with self.assertRaisesRegex(RuntimeError, "fetch"):
                    build.prepare_source()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_private_files_cannot_enter_source_export(self):
        checks = load("repo_check", "check-repo.py")
        for name in ("output/rootfs.tar.gz", "artifacts/connection.json", "tools/management-key", "config/key.pem"):
            with self.assertRaises(ValueError):
                checks.validate_public_path(name)

    def test_untested_kernel_cannot_replace_private_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            script = root / "tools/build-direct-release.py"
            script.write_bytes((TOOLS / script.name).read_bytes())
            package = root / "output/ec6108v9-armbian-r6-single"
            package.mkdir(parents=True)
            with (package / "rootfs.tar.gz").open("wb") as stream:
                stream.truncate(21 * 1024 * 1024)
            manifest = package / "manifest.json"
            manifest.write_text('{"keep": true}')
            (root / "output/kernel-manifest.json").write_text('{"tested_boot": false}')
            result = subprocess.run([sys.executable, str(script), "--private"],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no recorded boot validation", result.stderr)
            self.assertEqual(manifest.read_text(), '{"keep": true}')
            self.assertFalse((package / "uImage").exists())


if __name__ == "__main__":
    unittest.main()
