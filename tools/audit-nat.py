#!/usr/bin/env python3
"""Verify bridge, connection tracking and NAT using isolated real TCP traffic."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import time


def server(payload):
    data=Path(payload).read_bytes()
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Observed-Client',self.client_address[0])
            self.end_headers();self.wfile.write(data)
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']))
            result=json.dumps({'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
                               'observed_client':self.client_address[0]}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(result)))
            self.end_headers();self.wfile.write(result)
    http.server.HTTPServer(('10.203.2.2',18870),Handler).serve_forever()


def audit():
    def run(args,**kwargs):
        return subprocess.run(args,check=True,capture_output=True,text=True,timeout=25,**kwargs)
    token=secrets.token_hex(3)
    host_rules_before=run(['nft','list','ruleset']).stdout
    client,router,peer=('ec8c'+token,'ec8r'+token,'ec8s'+token)
    spaces=[];process=None
    scratch=Path(tempfile.mkdtemp(prefix='ec6108-nat-',dir='/run'))
    payload=scratch/'payload';payload.write_bytes(os.urandom(4*1048576))
    expected=hashlib.sha256(payload.read_bytes()).hexdigest()
    def ip(ns,*args):return run(['ip','-n',ns,*args])
    def execute(ns,*args,**kw):return run(['ip','netns','exec',ns,*args],**kw)
    def interrupted(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,interrupted)
    result={'kernel':os.uname().release,'bytes_each_direction':payload.stat().st_size,
            'sha256':expected,'topology':'client -> bridge/router -> peer; all three isolated namespaces'}
    try:
        for ns in (client,router,peer):
            run(['ip','netns','add',ns]);spaces.append(ns);ip(ns,'link','set','lo','up')
        ip(router,'link','add','lan0','type','veth','peer','name','client0')
        ip(router,'link','set','client0','netns',client)
        ip(router,'link','add','wan0','type','veth','peer','name','peer0')
        ip(router,'link','set','peer0','netns',peer)
        ip(router,'link','add','br0','type','bridge')
        ip(router,'link','set','lan0','master','br0')
        for ns,dev,address in ((client,'client0','10.203.1.2/24'),(router,'br0','10.203.1.1/24'),
                               (router,'wan0','10.203.2.1/24'),(peer,'peer0','10.203.2.2/24')):
            ip(ns,'address','add',address,'dev',dev);ip(ns,'link','set',dev,'up')
        ip(router,'link','set','lan0','up')
        ip(client,'route','add','default','via','10.203.1.1')
        execute(router,'sysctl','-qw','net.ipv4.ip_forward=1')
        process=subprocess.Popen(['ip','netns','exec',peer,sys.executable,str(Path(__file__).resolve()),
                                  '--server',str(payload)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for attempt in range(20):
            check=subprocess.run(['ip','netns','exec',router,'curl','-fsS','--max-time','1',
                                  'http://10.203.2.2:18870/','-o','/dev/null'],capture_output=True)
            if check.returncode==0:break
            if process.poll() is not None:raise RuntimeError('Peer server exited')
            time.sleep(.2)
        else:raise RuntimeError('Peer server did not become ready')
        # The peer has no route to the client subnet; a successful request needs NAT.
        negative=subprocess.run(['ip','netns','exec',client,'curl','-fsS','--connect-timeout','1',
                                 '--max-time','2','http://10.203.2.2:18870/','-o','/dev/null'],capture_output=True)
        if negative.returncode==0:raise RuntimeError('Negative control unexpectedly reached peer without NAT')
        result['without_nat_connection_failed']=True
        rules='''table inet ec6108_audit {
 chain forward {
  type filter hook forward priority filter; policy drop;
  ct state established,related counter accept
  iifname "br0" oifname "wan0" counter accept
 }
 chain postrouting {
  type nat hook postrouting priority srcnat; policy accept;
  oifname "wan0" ip saddr 10.203.1.0/24 counter masquerade
 }
}
'''
        execute(router,'nft','-f','-',input=rules)
        started=time.monotonic()
        execute(client,'curl','-fsS','--connect-timeout','3','--max-time','20',
                '-D',str(scratch/'headers'),'http://10.203.2.2:18870/','-o',str(scratch/'download'))
        if hashlib.sha256((scratch/'download').read_bytes()).hexdigest()!=expected:
            raise RuntimeError('NAT download checksum mismatch')
        headers=(scratch/'headers').read_text().lower()
        if 'x-observed-client: 10.203.2.1' not in headers:
            raise RuntimeError('Peer did not observe translated source address')
        upload=json.loads(execute(client,'curl','-fsS','--connect-timeout','3','--max-time','20',
                        '--data-binary','@'+str(payload),'http://10.203.2.2:18870/').stdout)
        if upload!={'bytes':4*1048576,'sha256':expected,'observed_client':'10.203.2.1'}:
            raise RuntimeError('NAT upload validation failed')
        result.update(download_sha256_matches=True,upload=upload,
                      transfer_seconds=round(time.monotonic()-started,3),
                      rules_and_counters=execute(router,'nft','list','ruleset').stdout,passed=True)
    finally:
        if process is not None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for ns in reversed(spaces):run(['ip','netns','delete',ns])
        for file in scratch.iterdir():file.unlink()
        scratch.rmdir()
    result['temporary_namespaces_removed']=True
    result['host_firewall_unchanged']=run(['nft','list','ruleset']).stdout==host_rules_before
    if not result['host_firewall_unchanged']:raise RuntimeError('Host firewall changed during the isolated test')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    if sys.argv[1:2]==['--server']:server(sys.argv[2])
    else:audit()
