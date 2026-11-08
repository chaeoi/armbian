#!/usr/bin/env python3
"""Export staged public adaptation sources only, excluding all working artifacts."""
# SPDX-License-Identifier: GPL-2.0-only
import gzip
import hashlib
import importlib.util
import io
import tarfile

from port import OUTPUT, PROJECT, SOURCE_INFO, git


def main():
    spec = importlib.util.spec_from_file_location("repo_check", PROJECT / "tools/check-repo.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    entries = git("ls-files", "--stage", "-z").split(b"\0")
    files = []
    for entry in filter(None, entries):
        metadata, raw_name = entry.split(b"\t", 1)
        mode, object_id, stage = metadata.split()
        name = raw_name.decode()
        checks.validate_public_path(name)
        if stage != b"0" or mode not in (b"100644", b"100755"):
            raise ValueError("Unsupported index entry: " + name)
        data = git("show", ":" + name)
        checks.validate_public_content(name, data)
        files.append((name, data, int(mode, 8) & 0o777))
    if not files or not any(name == "LICENSE" for name, _, _ in files):
        raise RuntimeError("Stage the public adaptation files in Git before exporting")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / "ec6108v9-armbian-port-source.tar.gz"
    with destination.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=SOURCE_INFO["source_date_epoch"]) as zipped:
            with tarfile.open(fileobj=zipped, mode="w|") as archive:
                for name, data, mode in sorted(files):
                    item = tarfile.TarInfo("ec6108v9-armbian/" + name)
                    item.size = len(data)
                    item.mode = mode
                    item.mtime = SOURCE_INFO["source_date_epoch"]
                    item.uid = item.gid = 0
                    item.uname = item.gname = "root"
                    archive.addfile(item, io.BytesIO(data))
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_name(destination.name + ".sha256").write_text(digest + "  " + destination.name + "\n")
    print("Exported", len(files), "public adaptation files:", destination)
    print("Upstream Linux is fetched separately using the included pinned source manifest.")


if __name__ == "__main__":
    main()
