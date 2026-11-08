#!/usr/bin/env python3
"""Transfer checksum-verified data over each box interface to this local PC."""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import shlex
import subprocess
import threading

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--label',required=True)
parser.add_argument('--scratch-root',default='/run',
                    help='Existing directory on the box for the transfer file')
args=parser.parse_args()
project=Path(__file__).resolve().parent.parent
payload=os.urandom(4*1024*1024)
expected=hashlib.sha256(payload).hexdigest()
uploads=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def do_POST(self):
        length=int(self.headers.get('Content-Length','0'))
        if length!=len(payload):self.send_error(400);return
        body=self.rfile.read(length)
        result={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
        uploads.append(result);encoded=json.dumps(result).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
interfaces=json.loads(subprocess.check_output(['ip','-j','address','show'],text=True))
addresses={entry['ifname']:next((x['local'] for x in entry.get('addr_info',[]) if x['family']=='inet'),None) for entry in interfaces}
server=http.server.ThreadingHTTPServer(('0.0.0.0',18766),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
results=[]
try:
    for box_if,pc_if in [('eth0','enp4s0'),('wlan0','wlp5s0')]:
        address=addresses.get(pc_if)
        if not address:raise RuntimeError('Local interface has no IPv4 address: '+pc_if)
        script=f'''set -eu
scratch=$(mktemp -d {shlex.quote(args.scratch_root.rstrip('/')+'/ec6108-network-audit.XXXXXX')})
trap 'rm -f "$scratch/payload"; rmdir "$scratch"' EXIT
curl --interface {shlex.quote(box_if)} --connect-timeout 5 --max-time 45 -fsS http://{address}:18766/payload -o "$scratch/payload" -w 'download_bytes=%{{size_download}} download_Bps=%{{speed_download}}\\n'
sync -d "$scratch/payload"
python3 -c 'import os,sys; f=open(sys.argv[1],"rb"); os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)' "$scratch/payload"
sha256sum "$scratch/payload"
python3 -c 'import os,sys; f=open(sys.argv[1],"rb"); os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)' "$scratch/payload"
curl --interface {shlex.quote(box_if)} --connect-timeout 5 --max-time 45 -fsS --data-binary @"$scratch/payload" http://{address}:18766/upload -w '\\nupload_bytes=%{{size_upload}} upload_Bps=%{{speed_upload}}\\n'
'''
        p=subprocess.run(['python3',str(project/'tools/box.py'),'run','sh','-c',script],capture_output=True,text=True,timeout=100)
        if p.returncode or expected not in p.stdout:raise RuntimeError(p.stdout+p.stderr)
        result={'interface':box_if,'peer':address,'scratch_root':args.scratch_root,
                'output':p.stdout,'sha256':expected,'passed':True}
        results.append(result);print(json.dumps(result),flush=True)
    assert len(uploads)==2 and all(x['sha256']==expected and x['bytes']==len(payload) for x in uploads)
finally:server.shutdown()
path=project/'artifacts/system-audit-20261106'/('network-'+args.label+'.json')
path.write_text(json.dumps({'results':results,'uploads':uploads},indent=2)+'\n')
