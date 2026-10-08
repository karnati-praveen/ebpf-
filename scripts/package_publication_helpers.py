"""Portable, checksummed archive helpers without campaign-completion claims."""
import hashlib
from pathlib import Path
import shutil
import zipfile

def copy_file(source,destination):
 if not source.is_file():raise RuntimeError(f'missing artifact: {source}')
 destination.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(source,destination)

def archive(staging,destination):
 files=sorted(p for p in staging.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
 hashes={p.relative_to(staging).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
 (staging/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in hashes.items()))
 pending=destination.with_suffix('.pending.zip')
 with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(staging.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(staging).as_posix())
 with zipfile.ZipFile(pending) as z:
  assert z.testzip() is None,'ZIP CRC failure'
  for name,digest in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
 pending.replace(destination)
 return {'file':destination.name,'bytes':destination.stat().st_size,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'files':len(hashes)+1,'crc_and_sha256_verified':True}
