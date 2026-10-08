#!/usr/bin/env python3
"""Package the editable paper, audited evidence and runnable demo separately."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from package_publication_helpers import archive, copy_file
ROOT=Path(__file__).resolve().parents[1]
PAPER=ROOT/'docs/publication'
OUTPUT=ROOT/'dist'
PACKAGE=OUTPUT/'shardwise_0.1.0+ci3.paper2_amd64.deb'

def main():
 build=json.loads((PAPER/'build-manifest.json').read_text())
 if build['pages']>10:raise RuntimeError('paper exceeds selected ten-page formatting target')
 for name,digest in build['sha256'].items():
  assert hashlib.sha256((PAPER/name).read_bytes()).hexdigest()==digest, name
 capture=json.loads((PAPER/'demo-screenshots/capture-manifest.json').read_text())
 for name,digest in capture['sha256'].items():
  assert hashlib.sha256((PAPER/'demo-screenshots'/name).read_bytes()).hexdigest()==digest,name
 assert capture['real_inference_verified'] and capture['worker_loss_verified'] and capture['worker_restore_verified']
 assert capture['illustration']['cpu_layers']==8 and capture['illustration']['gpu_layers']==16
 assert capture['illustration']['gpu_execution_verified'] is False
 assert hashlib.sha256(PACKAGE.read_bytes()).hexdigest()==capture['package']['sha256']
 OUTPUT.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='shardwise-paper-') as temp:
  stage=Path(temp)
  for name in ('main.tex','main.pdf','main.bbl','references.bib','ieee-template.tex','ieee-manuscript.md','build-manifest.json','README.md','READINESS.md'):
   copy_file(PAPER/name,stage/name)
  for folder in ('figures','demo-screenshots'):
   for p in (PAPER/folder).glob('*'):
    if p.is_file() and p.suffix in ('.png','.pdf','.json','.md'):copy_file(p,stage/folder/p.name)
  for name in ('IEEEtran.cls','IEEEtranN.bst'):
   copy_file(Path(subprocess.check_output(['kpsewhich',name],text=True).strip()),stage/name)
  # Rebuild from just the ZIP files, with the IEEE class and bibliography supplied.
  subprocess.run(['latexmk','-pdf','-interaction=nonstopmode','-halt-on-error','main.tex'],cwd=stage,check=True,stdout=subprocess.DEVNULL)
  log=(stage/'main.log').read_text()
  for text in ('undefined references','Citation `','Missing character:','Float too large','Overfull'):
   assert text not in log,text
  metadata=subprocess.check_output(['pdfinfo','main.pdf'],cwd=stage,text=True)
  assert int(re.search(r'Pages:\s+(\d+)',metadata)[1])==build['pages']
  # Deliver the verified repository PDF; temporary independent build checks portability.
  copy_file(PAPER/'main.pdf',stage/'main.pdf')
  copy_file(PAPER/'main.bbl',stage/'main.bbl')
  for suffix in ('.aux','.log','.blg','.fdb_latexmk','.fls','.out'):
   (stage/('main'+suffix)).unlink(missing_ok=True)
  (stage/'SUBMISSION_NOTES.md').write_text('''# Submission and author audit

The paper retains Anonymous Authors for the user to audit later. Upload the PDF
through the selected conference's submission system; the ZIP is an editable
source package, not an automatic submission. For CCGrid 2027, the current call
requires double-blind IEEE conference papers of no more than 10 pages including
references. Verify the chosen track and current rules before uploading.
Official call: https://hpcclab.org/ccgrid27-call-for-papers/

Actual CPU execution images and the CPU/GPU illustration have distinct captions.
The latter assigns CPU 8 / GPU 16 layers and is explicitly not measured GPU
execution. The evidence and remaining scientific limits are described in the
paper and READINESS.md. Review artifact anonymity and any disclosure requirements
referenced by the conference call; do not upload author-identifying demo
provenance as anonymous supplementary material without an anonymity audit.

The combined archive's demo is a separately versioned application artifact.
System-wide installation was not tested; launching its extracted payload was.
''')
  outputs=[archive(stage,OUTPUT/'shardwise-ieee-paper.zip')]
  copy_file(PACKAGE,stage/'demo-package'/PACKAGE.name)
  copy_file(PACKAGE.with_suffix('.provenance.json'),stage/'demo-package/package-provenance.json')
  (stage/'demo-package/README.md').write_text('''# Runnable Shardwise demo — Linux amd64

Install on Debian/Ubuntu amd64:

```bash
sudo apt install ./shardwise_0.1.0+ci3.paper2_amd64.deb
shardwise solo --device cpu
```

The launcher prints the local dashboard URL and attempts to open a browser.
On first launch it downloads its pinned Python environment and model, requiring
network access and several GiB of free disk/RAM. Stop the app with
`shardwise stop`. It also supplies a desktop launcher.

The live demo runs actual Qwen2.5-0.5B-Instruct inference and chooses one or two
local workers according to available memory. Stop/Restore buttons demonstrate
controller recovery when two workers are available. Local hostname labels read
CPU host. The navigation link CPU/GPU illustration opens a read-only page with
8 CPU layers and 16 GPU layers; it does not run or measure a GPU.

For rootless execution without installing:

```bash
mkdir extracted
dpkg-deb -x shardwise_0.1.0+ci3.paper2_amd64.deb extracted
SHARDWISE_BIN="$PWD/extracted/opt/shardwise/bin" \
  ./extracted/opt/shardwise/app/demo/shardwise solo --device cpu
```

The package's controller, node agent, router and worker runtime are unchanged
from release 0.1.0+ci3; presentation labels and the illustration were added.
Original release and final package hashes are in package-provenance.json.
This package is separate from the research runtime under source/.
''')
  (stage/'source').mkdir()
  for folder in ('bench','worker','internal','cmd','gen','proto','demo','scripts','deploy/standalone'):
   for p in (ROOT/folder).rglob('*'):
    if not p.is_file() or '__pycache__' in p.parts or 'results' in p.relative_to(ROOT/folder).parts:continue
    if p.suffix in ('.py','.go','.sh','.json','.html','.proto','.o','.txt','.md'):
     copy_file(p,stage/'source'/p.relative_to(ROOT))
  for name in ('go.mod','go.sum','Makefile','README.md','docs/TWO_LAPTOP_TESTS.md','docs/REPOSITORY_VERIFICATION.md'):
   copy_file(ROOT/name,stage/'source'/name)
  for folder in ('results/validation-2026-10-08','results/objective-aware-2026-10-04','docs/data/azure-vm-2026-10-04'):
   for p in (ROOT/folder).rglob('*'):
    if p.is_file() and p.suffix in ('.json','.jsonl','.csv','.txt','.md','.log','.py','.go') and '__pycache__' not in p.parts:
     copy_file(p,stage/'source'/p.relative_to(ROOT))
  (stage/'SHA256SUMS').unlink(missing_ok=True)
  outputs.append(archive(stage,OUTPUT/'shardwise-ieee-paper-and-demo.zip'))
 (OUTPUT/'ieee-delivery-manifest.json').write_text(json.dumps({'paper_pages':build['pages'],'format':'IEEEtran conference, letter paper','formatting_target':'CCGrid 2027 ten pages including references','author_metadata':'anonymous; user audit pending','gpu_view':'illustrative CPU 8 / GPU 16, not measured GPU execution','archives':outputs},indent=2)+'\n')
 print(json.dumps(outputs,indent=2))

if __name__=='__main__':main()
