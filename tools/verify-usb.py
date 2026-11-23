#!/usr/bin/env python3
"""Validate an EC6108V9 USB installer disk without connecting to a device."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zlib

from port import BOARD, PROJECT
from uimage import validate_image

sys.path.insert(0, str(PROJECT / "packages/bsp/ec6108v9"))
from kernel_package import PACKAGE, PAYLOAD, image_package_version
from sparse import inspect
from usb_disk import contents, DISK_LAYOUT
from usb_layout import boot_environment, flash_environment, flash_positions


def verify_defaults(filesystem, manifest, check_apt, check_first_login):
    def debugfs(command):
        return subprocess.check_output(["debugfs", "-R", command, str(filesystem)],
                                       text=True, stderr=subprocess.DEVNULL)

    def names(directory):
        return [line.split("/")[5] for line in debugfs(f"ls -p {directory}").splitlines()
                if line.startswith("/") and line.count("/") >= 6]

    fstab = [line.split() for line in debugfs("cat /etc/fstab").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(fstab) != 1 or fstab[0][:3] != [BOARD["layout"]["root_partition"], "/", "ext4"]:
        raise ValueError("Expected only the internal eMMC root in fstab")

    system_units = "/etc/systemd/system"
    entries = names(system_units)
    enabled = [unit for name in entries if name.endswith((".wants", ".requires"))
               for unit in names(f"{system_units}/{name}")]
    if (any(unit.startswith(("wpa_supplicant", "ec6108-wifi-")) for unit in enabled)
            or any(unit.endswith((".automount", ".mount")) for unit in entries + enabled)
            or "ec6108-wifi-power-save-off.service" in entries
            or "90-ec6108-wifi.rules" in names("/etc/udev/rules.d")
            or "20-wifi.network" in names("/etc/systemd/network")):
        raise ValueError("Unexpected automatic Wi-Fi or removable storage setup")
    if (any(name.endswith(".conf") for name in names("/etc/wpa_supplicant"))
            or set(names("/etc/NetworkManager/system-connections")) - {".", ".."}
            or any(re.search(r"^\s*wifis\s*:", debugfs(f"cat /etc/netplan/{name}"), re.M)
                   for name in names("/etc/netplan") if name.endswith(".yaml"))):
        raise ValueError("Unexpected Wi-Fi connection profile")

    if check_first_login:
        profile = debugfs("cat /etc/profile.d/armbian-check-first-login.sh")
        if (".not_logged_in_yet" not in names("/root")
                or debugfs("cat /root/.not_logged_in_yet")
                or "/usr/lib/armbian/armbian-firstlogin" not in profile
                or not debugfs("cat /usr/lib/armbian/armbian-firstlogin")
                or "00-ec6108v9-login.conf" in names("/etc/ssh/sshd_config.d")):
            raise ValueError("Expected the unconfigured Armbian first login wizard")
        password_hash = next((line.split(":")[1] for line in debugfs("cat /etc/shadow").splitlines()
                              if line.startswith("root:")), "")
        if not password_hash or subprocess.run(
            ["perl", "-e", 'my $hash = <STDIN>; chomp $hash; exit(crypt("1234", $hash) ne $hash);'],
            input=password_hash + "\n", text=True,
        ).returncode:
            raise ValueError("Image root password differs from the Armbian default")

    if check_apt:
        for source, destination in (
            ("ec6108v9.sources", "/etc/apt/sources.list.d/ec6108v9.sources"),
            ("ec6108v9-archive-keyring.asc", "/usr/share/keyrings/ec6108v9-archive-keyring.asc"),
        ):
            if debugfs("cat " + destination) != (PROJECT / "config/apt" / source).read_text():
                raise ValueError("APT source or signing key missing or different")
        status = debugfs("cat /var/lib/dpkg/status")
        stanzas = [block.splitlines() for block in status.split("\n\n")]
        expected_version = "Version: " + image_package_version(manifest)
        if not any({f"Package: {PACKAGE}", "Status: install ok installed", expected_version}
                   .issubset(stanza) for stanza in stanzas):
            raise ValueError("Image kernel is not installed as an APT package")
        fields = ("kernel_release", "kernel_bytes", "kernel_sha256")
        if json.loads(debugfs(f"cat /{PAYLOAD}/kernel.json")) != {key: manifest[key] for key in fields}:
            raise ValueError("Preinstalled APT kernel metadata differs from the boot image")
        packaged_kernel = subprocess.check_output(
            ["debugfs", "-R", f"cat /{PAYLOAD}/uImage", str(filesystem)], stderr=subprocess.DEVNULL)
        if hashlib.sha256(packaged_kernel).hexdigest() != manifest["kernel_sha256"]:
            raise ValueError("Preinstalled APT kernel differs from the boot image")


def verify(path, kernel_abi="", check_defaults=False, check_apt=False, check_first_login=False):
    checksum = path.with_name(path.name + ".sha")
    if checksum.exists() or path.name.endswith(".img.xz"):
        fields = checksum.read_text().split()
        sha = hashlib.sha256()
        with path.open("rb") as stream:
            while data := stream.read(1024 * 1024):
                sha.update(data)
        if len(fields) != 2 or fields[1].lstrip("*") != path.name or sha.hexdigest() != fields[0]:
            raise ValueError("USB disk image checksum differs")
    with contents(path) as package:
        manifest = json.loads((package / "manifest.json").read_text())
        if (manifest["image_type"] != "usb-installer" or manifest["profile"] != "mdmo1d"
                or manifest["board"] != "ec6108v9" or manifest["emmc_bytes"] != BOARD["emmc_bytes"]
                or manifest["disk"] != DISK_LAYOUT):
            raise ValueError("Unexpected board image")
        if kernel_abi and (not re.fullmatch(r"[1-9][0-9]{0,5}", kernel_abi)
                           or not manifest["kernel_release"].endswith(f"-ec6108v9.{kernel_abi}-edge-hi3798mv100")):
            raise ValueError("USB image lacks the requested EC6108V9 kernel ABI")
        positions = flash_positions(BOARD, manifest["rootfs"]["expanded_bytes"])
        if set(manifest["files"]) != set(positions):
            raise ValueError("Unexpected flashing file set")
        for key, (filename, sector, sectors) in positions.items():
            item = manifest["files"][key]
            if (item["filename"] != "mv100/" + filename or item["sector"] != sector
                    or item["sectors"] != sectors or item["sparse"] != (key == "root")):
                raise ValueError("USB flashing geometry differs")
        expected = {"fastboot.bin", "bootargs.bin", "manifest.json", "README.txt", "SHA256SUMS"}
        expected.update(item["filename"] for item in manifest["files"].values())
        actual = {item.relative_to(package).as_posix() for item in package.rglob("*") if item.is_file()}
        directories = {item.relative_to(package).as_posix() for item in package.rglob("*") if item.is_dir()}
        if actual != expected or directories != {"mv100"}:
            raise ValueError("Unexpected USB payload set")
        checksums = dict(line.split("  ", 1)[::-1] for line in (package / "SHA256SUMS").read_text().splitlines())
        if set(checksums) != expected - {"SHA256SUMS"}:
            raise ValueError("Incomplete checksum list")
        for name, checksum in checksums.items():
            digest = hashlib.sha256()
            with (package / name).open("rb") as stream:
                while data := stream.read(1024 * 1024):
                    digest.update(data)
            if digest.hexdigest() != checksum:
                raise ValueError("USB checksum mismatch: " + name)
        if (package / "bootargs.bin").read_bytes() != flash_environment(manifest["files"]):
            raise ValueError("USB flashing environment differs")
        if (package / "mv100/bootargs.bin").read_bytes() != boot_environment(BOARD):
            raise ValueError("Installed boot environment differs")
        loader = json.loads((PROJECT / "config/sources/usb-bootstrap.json").read_text())
        if hashlib.sha256((package / "fastboot.bin").read_bytes()).hexdigest() != loader["files"]["fastboot.bin"]["sha256"]:
            raise ValueError("BootROM loader differs")
        for item in manifest["files"].values():
            sha = hashlib.sha256()
            crc = 0
            file = package / item["filename"]
            if (file.stat().st_size != item["bytes"] or item["bytes"] <= 0
                    or (not item["sparse"] and item["bytes"] != item["sectors"] * 512)):
                raise ValueError("Bootloader payload size differs")
            with file.open("rb") as stream:
                while data := stream.read(1024 * 1024):
                    sha.update(data)
                    crc = zlib.crc32(data, crc)
            if sha.hexdigest() != item["sha256"] or crc != item["crc32"]:
                raise ValueError("Bootloader payload checksum differs")
            if item["sector"] < 0 or (item["sector"] + item["sectors"]) * 512 > BOARD["emmc_bytes"]:
                raise ValueError("Write exceeds eMMC bounds")
        kernel = (package / "mv100/kernel.bin").read_bytes()
        size = manifest["kernel_bytes"]
        validate_image(kernel[:size], BOARD["kernel_read_bytes"])
        if any(kernel[size:]):
            raise ValueError("Kernel partition padding is not zero")
        if hashlib.sha256(kernel[:size]).hexdigest() != manifest["kernel_sha256"]:
            raise ValueError("Kernel manifest digest differs")
        with (package / "mv100/rootfs.ext4").open("rb") as stream:
            if check_defaults or check_apt or check_first_login:
                with tempfile.TemporaryDirectory(prefix="ec6108-verify-") as temporary:
                    filesystem = Path(temporary) / "root.ext4"
                    with filesystem.open("wb") as expanded:
                        rootfs = inspect(stream, expanded)
                    verify_defaults(filesystem, manifest, check_apt, check_first_login)
            else:
                rootfs = inspect(stream)
        if rootfs != manifest["rootfs"]:
            raise ValueError("Sparse filesystem readback differs")
        sidecar = path.with_name(path.name.split(".img", 1)[0] + ".manifest.json")
        if sidecar.exists() and json.loads(sidecar.read_text()) != manifest:
            raise ValueError("Installer manifest sidecar differs")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-abi", default="")
    parser.add_argument("--check-defaults", action="store_true")
    parser.add_argument("--check-apt", action="store_true")
    parser.add_argument("--check-first-login", action="store_true")
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()
    for image in args.images:
        metadata = verify(image, args.kernel_abi, args.check_defaults, args.check_apt, args.check_first_login)
        print(image.name + ": verified; " + metadata["kernel_release"] + "; hardware boot test pending")
