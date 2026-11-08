#!/usr/bin/env python3
"""Use the PC's installed Ubuntu firmware, preserving merged-/usr symlinks."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

project = Path(__file__).resolve().parent.parent
output = project/'output'
base = output/'wifi-firmware'
destination = base/'lib/firmware/rtlwifi'
destination.mkdir(parents=True, exist_ok=True)
with (destination/'rtl8188eufw.bin').open('wb') as stream:
    subprocess.run(['zstd', '-q', '-d', '-c',
                    '/lib/firmware/rtlwifi/rtl8188eufw.bin.zst'], stdout=stream, check=True)
for name in ('regulatory.db', 'regulatory.db.p7s'):
    shutil.copy2(Path('/lib/firmware')/name, base/'lib/firmware'/name)
documentation = base/'usr/share/doc/ec6108-wifi-firmware'
documentation.mkdir(parents=True, exist_ok=True)
shutil.copy2('/usr/share/doc/linux-firmware/copyright', documentation/'copyright')
files = {}
archive_path = output/'wifi-firmware.tar'
with tarfile.open(archive_path, 'w') as archive:
    # Files only: directory headers could replace /lib -> usr/lib, or change
    # ownership of system directories to the PC user's numeric UID.
    for source in sorted(base.rglob('*')):
        if not source.is_file():
            continue
        name = source.relative_to(base).as_posix()
        if name.startswith('lib/'):
            name = 'usr/'+name
        item = archive.gettarinfo(str(source), arcname=name)
        item.uid = item.gid = 0
        item.uname = item.gname = 'root'
        item.mode = 0o644
        with source.open('rb') as stream:
            archive.addfile(item, stream)
        files[name] = hashlib.sha256(source.read_bytes()).hexdigest()
manifest = {
    'source': 'Locally installed Ubuntu linux-firmware and wireless-regdb',
    'packages': subprocess.check_output(
        ['dpkg-query', '-W', 'linux-firmware', 'wireless-regdb'], text=True).splitlines(),
    'files': files,
    'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
}
(output/'wifi-firmware-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print('Firmware archive and provenance prepared; no system directory headers included.')
