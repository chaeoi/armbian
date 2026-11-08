#!/usr/bin/env python3
"""Copy the PC's active WPA-PSK connection to the box without displaying secrets."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--interface', default='wlp5s0')
args = parser.parse_args()
project = Path(__file__).resolve().parent.parent

def nmcli(*arguments):
    return subprocess.check_output(['nmcli', '--escape', 'no', *arguments], text=True).rstrip('\n')

uuid = nmcli('-g', 'GENERAL.CON-UUID', 'device', 'show', args.interface)
ssid = nmcli('-g', '802-11-wireless.ssid', 'connection', 'show', uuid).encode()
key_mgmt = nmcli('-g', '802-11-wireless-security.key-mgmt', 'connection', 'show', uuid)
if key_mgmt != 'wpa-psk':
    raise SystemExit('The active connection is not a supported WPA-PSK profile')
password = nmcli('--show-secrets', '-g', '802-11-wireless-security.psk', 'connection', 'show', uuid)
if re.fullmatch('[0-9a-fA-F]{64}', password):
    psk = password.lower()
elif 8 <= len(password.encode()) <= 63:
    psk = hashlib.pbkdf2_hmac('sha1', password.encode(), ssid, 4096, 32).hex()
else:
    raise SystemExit('The connection password is unavailable or invalid')
configuration = (
    'ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev\n'
    'update_config=0\ncountry=CN\nnetwork={\n'
    f'    ssid={ssid.hex()}\n    psk={psk}\n'
    '    key_mgmt=WPA-PSK\n    scan_ssid=1\n}\n'
)
with tempfile.TemporaryDirectory(prefix='ec6108-wifi-') as private:
    profile = Path(private) / 'wifi.conf'
    profile.touch(mode=0o600)
    profile.write_text(configuration)
    subprocess.run(['python3', str(project/'tools/box.py'), 'upload', str(profile),
                    '/var/lib/armbian-port/wifi.conf'], check=True)
print('Copied the active PC Wi-Fi profile privately; no password displayed.')
