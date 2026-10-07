#!/usr/bin/env python3
"""Create compact, checksummed IEEE writing and demo screenshot ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PAPER=ROOT/'docs/publication'
OUTPUT=ROOT/'dist'


def copy(source,dest):
    if not source.is_file():raise RuntimeError(f'missing required artifact: {source}')
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,dest)


def archive(staging,destination):
    files=[p for p in staging.rglob('*') if p.is_file()]
    hashes={p.relative_to(staging).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    (staging/'SHA256SUMS').write_text(''.join(f'{v}  {k}\n' for k,v in hashes.items()))
    temporary=destination.with_suffix('.pending.zip')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(staging.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(staging).as_posix())
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:raise RuntimeError('ZIP CRC verification failed')
        for name,digest in hashes.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise RuntimeError(f'ZIP content mismatch: {name}')
    temporary.replace(destination)
    return {'filename':destination.name,'bytes':destination.stat().st_size,
            'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'files':len(hashes)+1,'crc_and_sha256_verified':True}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--main',type=Path,required=True)
    ap.add_argument('--engine',type=Path,required=True)
    ap.add_argument('--multistage',type=Path,required=True)
    args=ap.parse_args()
    for campaign in (args.main,args.engine,args.multistage):
        status=json.loads((campaign/'completion-status.json').read_text())
        analysis=json.loads((campaign/'analysis.json').read_text())
        if not status['complete'] or analysis['missing_runs']:raise RuntimeError(f'incomplete campaign: {campaign}')
    build=json.loads((PAPER/'build-manifest.json').read_text())
    for name,digest in build['sha256'].items():
        if hashlib.sha256((PAPER/name).read_bytes()).hexdigest()!=digest:raise RuntimeError(f'stale paper build: {name}')
    shots=PAPER/'demo-screenshots'
    capture=json.loads((shots/'capture-manifest.json').read_text())
    for name,digest in capture['sha256'].items():
        if hashlib.sha256((shots/name).read_bytes()).hexdigest()!=digest:raise RuntimeError(f'screenshot mismatch: {name}')
    if not capture.get('real_inference_verified') or not capture.get('worker_loss_verified'):
        raise RuntimeError('demo capture did not establish required execution and recovery')
    OUTPUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='shardwise-bundle-',dir=OUTPUT) as temp:
        stage=Path(temp)
        writing=stage/'writing';writing.mkdir()
        for name in ('main.tex','main.pdf','main.bbl','references.bib','ieee-template.tex','ieee-manuscript.md','build-manifest.json','README.md','READINESS.md'):
            copy(PAPER/name,writing/name)
        for p in (PAPER/'figures').glob('*'):
            if p.suffix in ('.pdf','.png','.svg'):copy(p,writing/'figures'/p.name)
        for name in ('IEEEtran.cls','IEEEtranN.bst'):
            path=subprocess.check_output(['kpsewhich',name],text=True).strip()
            copy(Path(path),writing/name)
        # Keep the repository's exact relative layout for existing analyzers.
        # Model weights, installs, caches, .git, unrelated research downloads and
        # previous generated ZIP exports are deliberately omitted.
        tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        for name in tracked:
            if not name or name.startswith(('new-evidence/','docs/publication/')):continue
            if name.endswith(('.zip','.deb','.pyc','.aux','.fdb_latexmk','.fls','.out','.blg')):continue
            p=ROOT/name
            if p.is_file():copy(p,writing/'source'/name)
        for directory in ('bench','scripts','worker','demo','internal/partition','internal/controller','cmd/partitionplan'):
            for p in (ROOT/directory).rglob('*'):
                if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc','.zip'):continue
                if directory=='bench' and 'results' in p.relative_to(ROOT/'bench').parts:continue
                copy(p,writing/'source'/p.relative_to(ROOT))
        for name in ('docs/TWO_LAPTOP_TESTS.md','docs/PUBLICATION_REVISION.md'):
            copy(ROOT/name,writing/'source'/name)
        for name in ('analyze.py','RESULTS_AUDIT.md'):
            copy(ROOT/'docs/paper/elsevier'/name,writing/'source/docs/paper/elsevier'/name)
        for p in (ROOT/'docs/paper/elsevier/analysis').glob('*'):
            if p.is_file():copy(p,writing/'source/docs/paper/elsevier/analysis'/p.name)
        evidence=ROOT/'results/publication-2026-10-07'
        for p in evidence.rglob('*'):
            if not p.is_file() or p.suffix in ('.pdf','.pyc') or p.name.startswith('.') or p.name.endswith('.pending'):continue
            copy(p,writing/'source'/p.relative_to(ROOT))
        for p in shots.rglob('*'):
            if p.is_file():copy(p,writing/'demo-screenshots'/p.relative_to(shots))
        # Model planner checks can run without Kubernetes/gRPC downloads.
        planner=writing/'planner-checks';planner.mkdir()
        (planner/'go.mod').write_text('module shardwise-planner-checks\n\ngo 1.26.1\n')
        for p in (ROOT/'internal/partition').glob('*.go'):copy(p,planner/p.name)
        (planner/'README.md').write_text('Run `go test ./...` here. These are cost-model checks, not serving performance evidence.\n')
        for p in (ROOT/'docs/publication').glob('manuscript-*.md'):copy(p,writing/'revision-history'/p.name)
        demo=stage/'demo';demo.mkdir()
        for p in shots.rglob('*'):
            if p.is_file():copy(p,demo/p.relative_to(shots))
        outputs=[archive(writing,OUTPUT/'shardwise-ieee-conference.zip'),archive(demo,OUTPUT/'shardwise-demo-screenshots.zip')]
    (OUTPUT/'manifest.json').write_text(json.dumps({'format':'general IEEE conference writing package; no venue submission performed','paper_pages':build['pages'],'archives':outputs},indent=2)+'\n')
    print(json.dumps(outputs,indent=2))


if __name__=='__main__':main()
