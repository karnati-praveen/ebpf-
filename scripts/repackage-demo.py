#!/usr/bin/env python3
"""Repackage the verified demo with anonymous labels and a labeled illustration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
EXPECTED='b7268ddeff783198b7971134bfbe5036027d763afcd8b68a9242bd1bb7002f4d'
VERSION='0.1.0+ci3.paper2'
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source-deb',type=Path,default=ROOT/'.publication-tools/release/shardwise_amd64.deb')
ap.add_argument('--output',type=Path,default=ROOT/f'dist/shardwise_{VERSION}_amd64.deb')
a=ap.parse_args()
os.umask(0o022)
assert hashlib.sha256(a.source_deb.read_bytes()).hexdigest()==EXPECTED,'unexpected source package'
a.output.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='shardwise-deb-') as temp:
 stage=Path(temp)
 stage.chmod(0o755)
 subprocess.run(['dpkg-deb','-x',str(a.source_deb),str(stage)],check=True)
 subprocess.run(['dpkg-deb','-e',str(a.source_deb),str(stage/'DEBIAN')],check=True)
 app=stage/'opt/shardwise/app/demo'
 p=app/'app.html';s=p.read_text()
 old='${esc(w.node)}';assert old in s
 s=s.replace(old,"${w.local?'CPU host':esc(w.node)}")
 s=s.replace('<button class="btn danger" id="exit">','<a class="btn" href="/illustration" target="_blank" rel="noopener">CPU/GPU illustration</a><button class="btn danger" id="exit">')
 p.write_text(s)
 shutil.copyfile(ROOT/'demo/cpu-gpu-illustration.html',app/'cpu-gpu-illustration.html')
 p=app/'app.py';s=p.read_text()
 marker="            elif self.path == '/api/status':"
 assert marker in s
 s=s.replace(marker,"            elif self.path == '/illustration': self.send(200, (ROOT/'demo/cpu-gpu-illustration.html').read_text(), True)\n"+marker)
 p.write_text(s)
 p=stage/'DEBIAN/control';p.write_text(p.read_text().replace('Version: 0.1.0+ci3',f'Version: {VERSION}'))
 (stage/'DEBIAN').chmod(0o755)
 for name in ('postinst','prerm','preinst','postrm'):
  path=stage/'DEBIAN'/name
  if path.exists():path.chmod(0o755)
 subprocess.run(['dpkg-deb','--root-owner-group','-b',str(stage),str(a.output)],check=True)
provenance={'version':VERSION,'filename':a.output.name,'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'bytes':a.output.stat().st_size,'original_sha256':EXPECTED,'original_url':'https://github.com/karnati-praveen/ebpf-/releases/download/shardwise-latest/shardwise_amd64.deb','changes':['local hostname presentation replaced with CPU host','read-only illustrative CPU/GPU page and navigation link'],'runtime_code':'worker backends, router, controller, node agent and launch setup unchanged from original release'}
a.output.with_suffix('.provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(json.dumps(provenance,indent=2))
