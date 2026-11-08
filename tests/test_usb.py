# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "packages/bsp/ec6108v9"))
from sparse import encode, inspect
from usb_layout import boot_environment, decode, flash_environment


class SparseTests(unittest.TestCase):
    def test_filesystem_bytes_survive_zero_and_raw_runs(self):
        data = b"A" * 4096 + bytes(4096 * 300) + bytes(range(256)) * 4096 + bytes(4096)
        output = io.BytesIO()
        self.assertEqual(encode(io.BytesIO(data), output), len(data))
        self.assertLess(len(output.getvalue()), len(data))
        output.seek(0)
        result = inspect(output)
        self.assertEqual(result["expanded_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["expanded_bytes"], len(data))

    def test_truncated_and_unaligned_files_are_rejected(self):
        with self.assertRaises(ValueError):
            encode(io.BytesIO(b"x" * 4097), io.BytesIO())
        image = io.BytesIO()
        encode(io.BytesIO(b"x" * 4096), image)
        for data in (image.getvalue()[:-1], image.getvalue() + b"extra"):
            with self.assertRaises(ValueError):
                inspect(io.BytesIO(data))

    def test_zero_blocks_are_written_instead_of_skipped(self):
        image = io.BytesIO()
        encode(io.BytesIO(bytes(4096 * 10)), image)
        self.assertEqual(struct.unpack_from("<H", image.getvalue(), 28)[0], 0xCAC2)


class USBEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.files = {key: {"filename": "mv100/" + key, "crc32": 1234, "sector": index * 0x1000,
                            "sectors": 0x1000, "sparse": key == "root"}
                      for index, key in enumerate(("root", "kernel", "base", "pq", "logo", "loader", "bootargs"))}
        self.values = decode(flash_environment(self.files))

    def run_flash(self, failure):
        # Model the loader's run, load, checksum and write commands with shell functions.
        functions = '''
run() { local key; for key in "$@"; do eval "${!key}" || return 1; done; }
fatload() { [[ "$4" != "$fail_file" ]]; }
crc32() { return 0; }
mw.l() { return 0; }
cmp.l() { [[ "$fail_crc" != yes ]]; }
mmc() { echo "WRITE $4"; [[ "$4" != "$fail_sector" ]]; }
reset() { echo RESET; }
'''
        assignments = []
        import shlex
        for key, value in self.values.items():
            assignments.append(key + "=" + shlex.quote(value))
        script = functions + "\n" + "\n".join(assignments) + "\neval \"$bootcmd\"\n"
        environment = {"fail_file": "", "fail_crc": "", "fail_sector": "", **failure}
        import os
        return subprocess.check_output(["bash", "-c", script], env={**os.environ, **environment}, text=True)

    def test_writes_begin_only_after_all_files_pass(self):
        for item in self.files.values():
            output = self.run_flash({"fail_file": item["filename"]})
            self.assertNotIn("WRITE", output)
            self.assertNotIn("RESET", output)
        output = self.run_flash({"fail_crc": "yes"})
        self.assertNotIn("WRITE", output)

    def test_boot_settings_are_written_last(self):
        output = self.run_flash({})
        writes = [line for line in output.splitlines() if line.startswith("WRITE")]
        self.assertEqual(len(writes), 7)
        self.assertEqual(writes[-1], "WRITE " + hex(self.files["bootargs"]["sector"]))
        self.assertIn("RESET", output)

    def test_failed_write_does_not_commit_boot_settings_or_reset(self):
        output = self.run_flash({"fail_sector": hex(self.files["kernel"]["sector"])})
        self.assertNotIn("WRITE " + hex(self.files["bootargs"]["sector"]), output)
        self.assertNotIn("RESET", output)

    def test_normal_environment_selects_only_the_new_root(self):
        board = json.loads((PROJECT / "config/boards/ec6108v9.json").read_text())
        data = boot_environment(board)
        values = decode(data)
        self.assertIn("root=/dev/mmcblk0p3", values["bootargs"])
        self.assertIn("0x7000 0x4000", values["bootcmd"])
        self.assertNotIn("fallback", " ".join(values))
        damaged = bytearray(data)
        damaged[100] ^= 1
        with self.assertRaises(ValueError):
            decode(damaged)


if __name__ == "__main__":
    unittest.main()
