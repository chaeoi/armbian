#!/usr/bin/env python3
"""Download and unpack the exact kernel archive, verifying its SHA-256 first."""
# SPDX-License-Identifier: GPL-2.0-only
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

from port import PROJECT, SOURCE, SOURCE_INFO, sha256


def main():
    receipt = SOURCE / ".ec6108-source.json"
    if SOURCE.exists():
        if receipt.exists() and json.loads(receipt.read_text()) == SOURCE_INFO:
            print("Pinned source already available:", SOURCE)
            return
        raise SystemExit("Existing source has no matching receipt; use an empty EC6108_SOURCE_DIR. "
                         "The existing tree was not changed.")
    cache = PROJECT / "downloads" / ("histb-linux-" + SOURCE_INFO["commit"] + ".tar.gz")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or sha256(cache) != SOURCE_INFO["archive_sha256"]:
        partial = cache.with_suffix(cache.suffix + ".part")
        try:
            print("Downloading", SOURCE_INFO["archive_url"], flush=True)
            with urllib.request.urlopen(SOURCE_INFO["archive_url"], timeout=60) as response:
                with partial.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
            if sha256(partial) != SOURCE_INFO["archive_sha256"]:
                raise RuntimeError("Kernel archive SHA-256 mismatch")
            partial.replace(cache)
        finally:
            partial.unlink(missing_ok=True)
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".kernel-", dir=SOURCE.parent) as temporary:
        unpacked = Path(temporary)
        with tarfile.open(cache) as archive:
            archive.extractall(unpacked, filter="data")
        roots = list(unpacked.iterdir())
        if len(roots) != 1 or not roots[0].is_dir() or not (roots[0] / "Makefile").is_file():
            raise RuntimeError("Unexpected kernel archive layout")
        (roots[0] / ".ec6108-source.json").write_text(json.dumps(SOURCE_INFO, indent=2) + "\n")
        roots[0].rename(SOURCE)
    print("Verified source:", SOURCE)


if __name__ == "__main__":
    main()
