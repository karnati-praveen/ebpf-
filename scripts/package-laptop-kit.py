#!/usr/bin/env python3
"""Package the small two-laptop kit, excluding dependencies and model weights."""
from pathlib import Path
import hashlib
import json
import zipfile
ROOT=Path(__file__).resolve().parents[1]
files=[ROOT/'docs/TWO_LAPTOP_TESTS.md']+[ROOT/'bench'/n for n in ('lan_agent.py','lan_publication.py','local_publication.py','publication_analyze.py')]
files.extend(p for p in (ROOT/'worker').rglob('*.py') if '__pycache__' not in p.parts)
files.append(ROOT/'proto/pipeline.proto')
entries={('README.md' if p.name=='TWO_LAPTOP_TESTS.md' else p.relative_to(ROOT).as_posix()):p.read_bytes() for p in files}
entries['SHA256SUMS']=''.join(f'{hashlib.sha256(b).hexdigest()}  {n}\n' for n,b in sorted(entries.items())).encode()
output=ROOT/'dist';output.mkdir(exist_ok=True)
destination=output/'shardwise-two-laptop-test-kit.zip'
with zipfile.ZipFile(destination.with_suffix('.pending.zip'),'w',zipfile.ZIP_DEFLATED) as z:
    for n,b in sorted(entries.items()):z.writestr(n,b)
with zipfile.ZipFile(destination.with_suffix('.pending.zip')) as z:
    assert z.testzip() is None
    for n,b in entries.items():assert z.read(n)==b
destination.with_suffix('.pending.zip').replace(destination)
(output/'laptop-kit-manifest.json').write_text(json.dumps({'filename':destination.name,'bytes':destination.stat().st_size,
    'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'files':len(entries),
    'scope':'Linux/WSL instructions and source kit; actual physical-laptop trials must be collected by users'},indent=2)+'\n')
print(destination, destination.stat().st_size,'bytes, CRC and contents verified')
