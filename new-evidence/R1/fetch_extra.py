import requests,pathlib,concurrent.futures,subprocess,json
from bs4 import BeautifulSoup
p=pathlib.Path('new-evidence/R1/sources')
def get(k,aid):
 r=requests.get('https://arxiv.org/abs/'+aid,timeout=20);r.raise_for_status();b=BeautifulSoup(r.text,'html.parser');d={'arxiv':aid}
 for m in b.find_all('meta'):
  n=m.get('name','')
  if n.startswith('citation_'):d.setdefault(n,[]).append(m.get('content',''))
 (p/(k+'-metadata.json')).write_text(json.dumps(d,indent=2));r=requests.get('https://arxiv.org/pdf/'+aid,timeout=25);r.raise_for_status();(p/(k+'.pdf')).write_bytes(r.content);subprocess.run(['pdftotext','-raw',str(p/(k+'.pdf')),str(p/(k+'-raw.txt'))],check=True);return k
with concurrent.futures.ThreadPoolExecutor() as ex:
 for f in [ex.submit(get,'wisp2026','2601.11652'),ex.submit(get,'llmpq2024','2403.01136')]:
  try:print(f.result())
  except Exception as e:print(type(e).__name__,str(e))
for k,doi in [('planck2024','10.1109/ICWS62655.2024.00157'),('costaware2025','10.1109/ACCESS.2025.3592308')]:
 try:
  r=requests.get('https://api.crossref.org/works/'+doi,timeout=15);r.raise_for_status();d=r.json()['message'];(p/(k+'-metadata.json')).write_text(json.dumps(d,indent=2));print(k,d['title'],d['author'])
 except Exception as e:print(k,str(e))
