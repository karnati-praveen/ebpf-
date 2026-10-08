import json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'bench'))
from multistage_publication import ThreeRuntime
from local_publication import trial
out=Path(__file__).resolve().parent/'replicas-isolated-retest'
out.mkdir(exist_ok=True)
source=out.parent/'three-worker-functional-serial'
manifest=json.loads((source/'manifest.json').read_text())
expected=json.loads((source/'reference.json').read_text())['256']
prompt=manifest['prompts']['256']
(out/'manifest.json').write_text(json.dumps({'scope':'fresh-runtime correctness retest of failed three-replica conditions; reference loaded from prior artifact without running a reference model in the driver','model':manifest['model'],'cpus':manifest['cpus'],'source':str(source),'concurrency':[8,4],'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2)+'\n')
passed=True
with (out/'runs.jsonl').open('w') as log:
 for q in (8,4):
  with ThreeRuntime('replicas-3x1t',[[0,28]]*3,manifest['model'],out/f'q{q}',manifest['cpus'],56000) as runtime:
   row=trial(runtime,prompt,expected,q,max(4,q))
   row.update(concurrency=q,mode='replicas-3x1t',context=256,output_tokens=32)
   log.write(json.dumps(row)+'\n');log.flush()
   alive=all(p.poll() is None for p in runtime.processes)
   passed &= row['failures']==0 and alive
   print(f'Q={q} failures={row["failures"]} workers_alive={alive}',flush=True)
(out/'status.json').write_text(json.dumps({'passed':passed,'conditions':2},indent=2)+'\n')
sys.exit(0 if passed else 1)
