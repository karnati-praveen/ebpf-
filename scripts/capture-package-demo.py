#!/usr/bin/env python3
"""Capture the actual .deb UI and verify its worker-stop recovery sequence."""
import hashlib
import json
import urllib.request
from pathlib import Path
import time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
SHOTS=ROOT/'docs/publication/demo-screenshots'
SHOTS.mkdir(exist_ok=True)
# A previous launch can leave a stale state file; wait for a reachable app.
for attempt in range(180):
 try:
  info=json.loads((ROOT/'.publication-tools/package-demo/state/app.json').read_text())
  url=f"http://127.0.0.1:{info['port']}"
  with urllib.request.urlopen(url+'/api/status',timeout=2) as response:
   json.load(response)
  break
 except (OSError,ValueError):
  time.sleep(1)
else:
 raise RuntimeError('package dashboard did not become reachable')
records=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1240,'height':920},device_scale_factor=2)
 page.goto(url,wait_until='networkidle')
 page.wait_for_function("() => status && status.app_state==='ready' && status.workers.filter(w=>w.status==='up'&&w.layers).length===2",timeout=180000)
 before_requests=page.evaluate('status.metrics.requests')
 page.locator('#prompt').fill('Explain pipeline parallelism in one sentence.')
 with page.expect_response(lambda r:r.url.endswith('/api/chat'),timeout=180000) as response:
  page.locator('#send').click()
 reply=response.value.json()
 assert response.value.status==200 and reply.get('text'),reply
 page.wait_for_function('() => !busy && history.length>=2',timeout=180000)
 page.wait_for_function('(previous) => status.metrics.requests>previous && status.telemetry.history.length>0',arg=before_requests,timeout=30000)
 page.screenshot(path=str(SHOTS/'01-real-chat-two-workers.png'),full_page=False)
 placement=page.get_by_role('region',name='Model placement')
 # Sections without an accessible heading do not expose region roles.
 placement=page.locator('section[aria-label="Model placement"]')
 placement.screenshot(path=str(SHOTS/'02-two-worker-placement.png'))
 records.append({'phase':'two-worker-chat','status':page.evaluate('status'),'chat_reply':reply})
 page.get_by_role('button',name='Stop w2',exact=True).click()
 page.wait_for_function("() => status && status.workers.some(w=>w.name==='w2'&&w.status==='stopped')",timeout=30000)
 page.screenshot(path=str(SHOTS/'03-worker-stopped.png'),full_page=False)
 page.wait_for_function("() => status && status.app_state==='ready' && status.workers.some(w=>w.name==='w1'&&w.layers&&w.layers[0]===0&&w.layers[1]===24) && status.workers.some(w=>w.name==='w2'&&!w.layers)",timeout=180000)
 placement.screenshot(path=str(SHOTS/'04-recovered-full-model.png'))
 before_requests=page.evaluate('status.metrics.requests')
 page.locator('#prompt').fill('In one sentence, why can fewer workers still run a small model?')
 with page.expect_response(lambda r:r.url.endswith('/api/chat'),timeout=180000) as response:
  page.locator('#send').click()
 recovery_reply=response.value.json()
 assert response.value.status==200 and recovery_reply.get('text'),recovery_reply
 page.wait_for_function('() => !busy && history.length>=4',timeout=180000)
 page.wait_for_function('(previous) => status.metrics.requests>previous',arg=before_requests,timeout=30000)
 page.screenshot(path=str(SHOTS/'05-chat-after-recovery.png'),full_page=False)
 records.append({'phase':'recovered-chat','status':page.evaluate('status'),'chat_reply':recovery_reply})
 page.get_by_role('button',name='Restore w2',exact=True).click()
 page.wait_for_function("() => status && status.app_state==='ready' && status.workers.filter(w=>w.status==='up'&&w.layers&&w.layers[1]>w.layers[0]).length===2",timeout=180000)
 placement.screenshot(path=str(SHOTS/'06-restored-split.png'))
 records.append({'phase':'restored','status':page.evaluate('status')})
 assert 'codespaces' not in page.locator('body').inner_text().lower()
 illustration=browser.new_page(viewport={'width':1240,'height':850},device_scale_factor=2)
 illustration.goto(url+'/illustration',wait_until='networkidle')
 text=illustration.locator('body').inner_text()
 assert 'w1 · CPU worker' in text and 'w2 · GPU worker' in text and 'codespaces' not in text.lower()
 assert 'no GPU execution or measurements' in text
 illustration.screenshot(path=str(SHOTS/'07-cpu-gpu-illustration.png'),full_page=True)
 browser.close()
(SHOTS/'execution-records.json').write_text(json.dumps(records,indent=2)+'\n')
release=json.loads((ROOT/'.publication-tools/release/download-provenance.json').read_text())
manifest={'capture_date':'2026-10-08','source':'actual Debian-package UI; presentation-only local hostname label changed to CPU host','original_package':release,'package':{'filename':'shardwise_0.1.0+ci3.paper2_amd64.deb','sha256':hashlib.sha256((ROOT/'dist/shardwise_0.1.0+ci3.paper2_amd64.deb').read_bytes()).hexdigest()},'hostname_label':'CPU host (presentation-only anonymization; both workers on one physical host)','model':'Qwen/Qwen2.5-0.5B-Instruct','model_revision':'7ae557604adf67be50417f59c2c2f167def9a775','runtime':'package-managed CPU runtime; separate from research environment','viewport':{'width':1240,'height':920,'device_scale_factor':2},'illustration':{'filename':'07-cpu-gpu-illustration.png','cpu_layers':8,'gpu_layers':16,'gpu_execution_verified':False,'label':'Illustrative CPU/GPU configuration — no GPU execution or measurements'},'real_inference_verified':True,'worker_loss_verified':True,'worker_restore_verified':True,'scope':'two worker processes on one CPU host; manual stop/restore controls; screenshots are execution evidence, not comparative performance','sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in SHOTS.glob('*.png')}}
(SHOTS/'capture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Captured actual package UI, two successful chats, worker loss recovery and restored split.')
