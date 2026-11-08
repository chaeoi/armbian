#!/usr/bin/env python3
"""Use the established SSH connection without storing a login password."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run", help="Run a command on the box")
    run.add_argument("command", nargs=argparse.REMAINDER)
    script = commands.add_parser("script", help="Run a local shell script on the box")
    script.add_argument("path", type=Path)
    upload = commands.add_parser("upload", help="Upload a file")
    upload.add_argument("local", type=Path)
    upload.add_argument("remote")
    download = commands.add_parser("download", help="Download a file")
    download.add_argument("remote")
    download.add_argument("local", type=Path)
    args = parser.parse_args()

    project = Path(__file__).resolve().parent.parent
    connection = json.loads((project / "artifacts/connection.json").read_text())
    identity = project / "artifacts/ec6108-management-key"
    transport = (["-i", str(identity), "-o", "IdentitiesOnly=yes"] if identity.exists()
                 else ["-S", connection["control_path"]])
    ssh = [
        "ssh", "-6", *transport,
        "-o", "ControlMaster=no", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + connection["known_hosts"],
        "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2", connection["host"],
    ]
    if args.action == "run":
        if not args.command:
            parser.error("run requires a command")
        return subprocess.run(ssh + [shlex.join(args.command)]).returncode
    if args.action == "script":
        with args.path.open("rb") as source:
            return subprocess.run(ssh + ["sh -s"], stdin=source).returncode
    if args.action == "upload":
        with args.local.open("rb") as source:
            return subprocess.run(
                ssh + ["umask 077; cat > " + shlex.quote(args.remote)], stdin=source
            ).returncode
    descriptor = os.open(args.local, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as destination:
        return subprocess.run(
            ssh + ["cat -- " + shlex.quote(args.remote)], stdout=destination
        ).returncode


if __name__ == "__main__":
    sys.exit(main())
