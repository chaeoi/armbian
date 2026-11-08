"""Shared paths and immutable inputs for the EC6108V9 host build tools."""
# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
BOARD = json.loads((PROJECT / "config/boards/ec6108v9.json").read_text())
SOURCE_INFO = json.loads((PROJECT / BOARD["kernel_source"]).read_text())


def directory(variable, default):
    value = Path(os.environ.get(variable, default)).expanduser()
    return (PROJECT / value).resolve() if not value.is_absolute() else value.resolve()


SOURCE = directory("EC6108_SOURCE_DIR", "work/histb-linux-source")
BUILD = directory("EC6108_BUILD_DIR", "work/kernel-build")
OUTPUT = directory("EC6108_OUTPUT_DIR", "output")
PATCHES = PROJECT / Path(BOARD["patch_series"]).parent


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*arguments):
    """Use system Git, or the optional original host's unpacked Git."""
    executable = shutil.which("git")
    environment = os.environ.copy()
    if executable is None:
        executable = str(PROJECT / "work/build-tools/usr/bin/git")
        environment["PATH"] = str(PROJECT / "work/build-tools/usr/bin") + os.pathsep + environment["PATH"]
        environment["GIT_EXEC_PATH"] = str(PROJECT / "work/build-tools/usr/lib/git-core")
        environment["LD_LIBRARY_PATH"] = str(PROJECT / "work/build-tools/usr/lib/x86_64-linux-gnu")
    return subprocess.check_output([executable, "-C", str(PROJECT), *arguments], env=environment)
