#!/usr/bin/env python3
"""Archive the selected kernel modules with stable timestamps and root ownership."""
# SPDX-License-Identifier: GPL-2.0-only
import json
import os
import tarfile

from port import BUILD, OUTPUT, SOURCE_INFO, sha256


def main():
    release = (BUILD / "include/config/kernel.release").read_text().strip()
    base = OUTPUT / "kernel-modules"
    directory = base / "lib/modules" / release
    if not directory.is_dir():
        raise RuntimeError("Install modules before packaging")
    for name in ("build", "source"):
        path = directory / name
        if path.is_symlink():
            path.unlink()

    def metadata(item):
        item.uid = item.gid = 0
        item.uname = item.gname = "root"
        item.mtime = int(os.environ.get("SOURCE_DATE_EPOCH", SOURCE_INFO["source_date_epoch"]))
        item.mode = 0o755 if item.isdir() else 0o644
        return item

    with tarfile.open(OUTPUT / "kernel-modules.tar", "w") as archive:
        archive.add(directory, arcname="lib/modules/" + release, filter=metadata)
    manifest = {str(path.relative_to(base)): sha256(path)
                for path in sorted(directory.rglob("*")) if path.is_file()}
    (OUTPUT / "kernel-modules-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    names = ["uImage-ec6108v9", "hi3798mv100-ec6108v9.dtb", "kernel.config",
             "kernel-manifest.json", "kernel-modules.tar", "kernel-modules-manifest.json"]
    (OUTPUT / "kernel-SHA256SUMS").write_text(
        "".join(sha256(OUTPUT / name) + "  " + name + "\n" for name in names))
    print("Packaged", len(manifest), "module files for", release)


if __name__ == "__main__":
    main()
