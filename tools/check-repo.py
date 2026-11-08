#!/usr/bin/env python3
"""Offline validation of the public adaptation tree; never contacts the box."""
# SPDX-License-Identifier: GPL-2.0-only
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.parse

from port import BOARD, PROJECT, SOURCE_INFO, git

PUBLIC_DIRECTORIES = {"config", "dts", "patch", "docs", "tools", "tests", ".github", "extensions", "packages"}
PUBLIC_FILES = {"README.md", "LICENSE", "NOTICE.md", "CONTRIBUTING.md", "CHANGELOG.md",
                "compile.sh", ".gitignore", ".gitattributes", ".editorconfig"}


def validate_public_path(name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Invalid source path: " + name)
    if name not in PUBLIC_FILES and path.parts[0] not in PUBLIC_DIRECTORIES:
        raise ValueError("Unexpected file in publication set: " + name)
    if any(part == "__pycache__" for part in path.parts) or path.suffix in {
            ".pyc", ".tar", ".gz", ".deb", ".pem", ".key"}:
        raise ValueError("Private/generated file in publication set: " + name)
    if path.suffix in {".bin", ".img"} and name not in public_blobs():
        raise ValueError("Unregistered binary in publication set: " + name)
    if path.name in {"connection.json", "known_hosts", "management-key", "authorized_keys"}:
        raise ValueError("Device identity in publication set: " + name)


def public_blobs():
    result = {}
    for name in ("usb-bootstrap.json", "ec6108v9-firmware.json"):
        path = PROJECT / "config/sources" / name
        if path.is_file():
            for item in json.loads(path.read_text())["files"].values():
                if not item["path"].startswith("packages/blobs/hi3798mv100/"):
                    raise ValueError("Boot asset outside the board blob directory")
                result[item["path"]] = item
    return result


def validate_public_content(name, data):
    if name in public_blobs():
        item = public_blobs()[name]
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Public board blob differs from its pinned manifest: " + name)
        return
    text = data.decode("utf-8")
    if re.search(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----", text):
        raise ValueError("Private key in " + name)
    if re.search(r"(?:^|\s)ssh-(?:ed25519|rsa) [A-Za-z0-9+/]{40,}", text):
        raise ValueError("Device login key in " + name)


def main():
    if (PROJECT / ".git").exists():
        names = set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")) - {""}
    else:
        # A source archive has no .git directory but must still be checkable.
        names = {name for name in PUBLIC_FILES if (PROJECT / name).is_file()}
        names.update(path.relative_to(PROJECT).as_posix()
                     for directory in PUBLIC_DIRECTORIES
                     for path in (PROJECT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts)
    names = {name for name in names if (PROJECT / name).exists() or (PROJECT / name).is_symlink()}
    if not names:
        raise RuntimeError("No public source files found")
    for name in sorted(names):
        validate_public_path(name)
        path = PROJECT / name
        if path.is_symlink():
            raise ValueError("Unexpected source symlink: " + name)
        data = path.read_bytes()
        validate_public_content(name, data)
        if path.suffix == ".py":
            ast.parse(data, filename=name)
        elif path.suffix == ".json":
            json.loads(data)
        elif path.suffix in {".sh", ".tvb", ".conf"}:
            subprocess.run(["bash", "-n", str(path)], check=True)
        elif path.suffix == ".md":
            for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", data.decode()):
                if "://" in target or target.startswith("#"):
                    continue
                target = urllib.parse.unquote(target.split("#", 1)[0])
                if not (path.parent / target).exists():
                    raise ValueError(f"Broken local link in {name}: {target}")
    for key in ("kernel_source", "kernel_config", "patch_series", "dts"):
        if BOARD[key] not in names:
            raise ValueError("Board input is not public: " + BOARD[key])
    if not re.fullmatch(r"[0-9a-f]{40}", SOURCE_INFO["commit"]):
        raise ValueError("Kernel source must be pinned to a full commit")
    if not re.fullmatch(r"[0-9a-f]{64}", SOURCE_INFO["archive_sha256"]):
        raise ValueError("Missing source archive SHA-256")
    patches = json.loads((PROJECT / BOARD["patch_series"]).read_text())
    patch_dir = Path(BOARD["patch_series"]).parent
    listed = []
    for item in patches:
        name = (patch_dir / item["patch"]).as_posix()
        if name not in names or name in listed:
            raise ValueError("Missing or duplicate patch: " + name)
        listed.append(name)
        for change in item.get("files", [item]):
            if not re.fullmatch(r"[0-9a-f]{64}", change["patched_sha256"]):
                raise ValueError("Missing patched source digest")
    actual = {p.relative_to(PROJECT).as_posix() for p in (PROJECT / patch_dir).glob("*.patch")}
    if set(listed) != actual:
        raise ValueError("Patch series does not match patch files")
    if BOARD["layout"]["kernel_offset"] + BOARD["layout"]["kernel_partition_bytes"] != BOARD["layout"]["root_offset"]:
        raise ValueError("Kernel/root layout has a gap or overlap")
    print("Checked", len(names), "public files; source pin, patches, syntax, links and publication paths passed.")


if __name__ == "__main__":
    main()
