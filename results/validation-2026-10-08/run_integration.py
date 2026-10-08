import json, os, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
python=str(root/'.publication-tools/venv/bin/python')
env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',TORCH_THREADS='1',HF_HUB_OFFLINE='1',PYTHONUNBUFFERED='1')
model=(root/'.publication-tools/model-path.txt').read_text().strip()
commands=[
 ('qwen-e2e',[python,'bench/verify_qwen3.py','--tokens','16']),
 ('recovery',[python,'bench/recovery_matrix.py','--out',str(out/'recovery'),'--model',model]),
 ('baseline-functional',[python,'bench/local_publication.py','--out',str(out/'baseline-functional'),'--repetitions','1','--contexts','32,128','--concurrency','1,2,4,8','--tokens','16','--requests','4','--model',model]),
 ('baseline-analysis',[python,'bench/publication_analyze.py',str(out/'baseline-functional')]),
 ('component-profile',[python,'bench/profile_qwen3.py','--model',model,'--device','cpu','--contexts','256','--warmup','2','--samples','5','--out',str(out/'component-profile.json')]),
 ('planner-build',['go','build','-o',str(out/'partitionplan'),'./cmd/partitionplan']),
 ('three-worker-functional',[python,'bench/multistage_publication.py','--out',str(out/'three-worker-functional-serial'),'--model',model,'--profile',str(out/'component-profile.json'),'--planner',str(out/'partitionplan'),'--repetitions','1']),
 ('three-worker-analysis',[python,'bench/publication_analyze.py',str(out/'three-worker-functional-serial')]),
]
status=out/'integration-status.json'
rows=json.loads(status.read_text()) if status.exists() else []
for name,command in commands:
    if any(row['name']==name and row['exit_code']==0 for row in rows):
        continue
    print('START '+name,flush=True)
    start=time.time()
    with (out/(name+'.log')).open('w') as log:
        result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    rows.append(dict(name=name,command=command,exit_code=result.returncode,elapsed_s=time.time()-start))
    (out/'integration-status.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('END '+name+' exit='+str(result.returncode),flush=True)
    if result.returncode:
        sys.exit(result.returncode)
