#!/usr/bin/env python3
"""Fetch a pinned official Armbian armhf Ubuntu 22.04 rootfs cache."""

import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request


REPOSITORY = "armbian/os/rootfs-armhf-jammy-minimal"
TAG = "202605-2069cd1b0d77-H6eccde-Bd966a5"
MANIFEST_SHA256 = "147857ee064ba3debd9c8c3c17fb7c06457e629130ce8d18ff0834c9e2884e2e"


def sha256(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def main():
    directory = Path(__file__).resolve().parent.parent / "downloads"
    directory.mkdir(exist_ok=True)
    query = urllib.parse.urlencode({
        "service": "ghcr.io", "scope": "repository:" + REPOSITORY + ":pull"
    })
    with urllib.request.urlopen("https://ghcr.io/token?" + query, timeout=30) as response:
        token = json.load(response)["token"]
    headers = {"Authorization": "Bearer " + token}
    request = urllib.request.Request(
        "https://ghcr.io/v2/" + REPOSITORY + "/manifests/" + TAG,
        headers={**headers, "Accept": "application/vnd.oci.image.manifest.v1+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        manifest_bytes = response.read()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise RuntimeError("Rootfs manifest does not match the pinned digest")
    manifest = json.loads(manifest_bytes)
    (directory / "rootfs-manifest.json").write_bytes(manifest_bytes)
    for layer in manifest["layers"]:
        filename = layer["annotations"]["org.opencontainers.image.title"]
        if filename != Path(filename).name:
            raise RuntimeError("Unexpected artifact filename")
        destination = directory / filename
        expected = layer["digest"].removeprefix("sha256:")
        if destination.exists() and sha256(destination) == expected:
            print("Already verified:", destination, flush=True)
            continue
        request = urllib.request.Request(
            "https://ghcr.io/v2/" + REPOSITORY + "/blobs/" + layer["digest"],
            headers=headers,
        )
        partial = destination.with_name(destination.name + ".part")
        received = 0
        next_progress = 16 * 1024 * 1024
        with urllib.request.urlopen(request, timeout=45) as response, partial.open("wb") as output:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                output.write(block)
                received += len(block)
                if received >= next_progress:
                    print("Downloaded", received, "of", layer["size"], "bytes", flush=True)
                    next_progress += 16 * 1024 * 1024
        if received != layer["size"] or sha256(partial) != expected:
            raise RuntimeError("Rootfs size or SHA-256 mismatch")
        partial.replace(destination)
        print("Verified:", destination, flush=True)


if __name__ == "__main__":
    main()
