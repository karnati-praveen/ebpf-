import csv,json,re,pathlib
p=pathlib.Path(__file__).parent
rows=[]
for name in ['edge-rows.csv','migration-rows.csv','root-rows.csv']:
 rows.extend(csv.DictReader((p/name).open()))
cols=list(rows[0]);seen=set();rows=[r for r in rows if not(r['work_id'] in seen or seen.add(r['work_id']))]
for k,title,aid,year,setup,gran,number,quote in [
('wisp2026','WISP: Waste- and Interference-Suppressed Distributed Speculative LLM Serving at the Edge via Dynamic Drafting and SLO-Aware Batching','2601.11652v2',2026,'Abstract:edge drafting/cloud verification; exact physical devices vs numerical simulation UNVERIFIED;full PDF saved but technical audit incomplete','Speculative token drafting and server batching','Abstract: capacity up to2.1x versus centralized/4.1x versusSLED;goodput1.94x/3.7x;exactsetup UNVERIFIED','These components collaboratively enhance drafting efficiency and optimize verification request scheduling on the server.'),
('llmpq2024','LLM-PQ: Serving LLM on Heterogeneous Clusters with Phase-Aware Partition and Adaptive Quantization','2403.01136',2024,'Abstract:11differentheterogeneousclusters;exactphysicalGPUconfiguration UNVERIFIED;fullPDF saved but technical audit incomplete','Mixed-precisionquantization, phase-aware layer partition andmicrobatch','Abstract:up to2.88x/average2.26x throughput;exact per-configuration baseline/setup UNVERIFIED','')]:
 r={c:'UNVERIFIED' for c in cols};r.update(work_id=k,title=title,year=str(year),venue='arXiv preprint; LLM-PQ also PPoPP2024 POSTER (final poster DOI UNVERIFIED)' if k=='llmpq2024' else 'arXiv preprint',status='PREPRINT',identifier='arXiv:'+aid,source_url='https://arxiv.org/abs/'+aid,hardware_and_setup=setup,granularity=gran,headline_results=number,evidence_quotes_and_locations=('“'+quote+'” — Abstract' if quote else 'UNVERIFIED exact claim sentence'),verification_gaps='Metadata and abstract verified; full technical extraction not completed');rows.append(r)
for k in ['planck2024','costaware2025']:
 d=json.loads((p/'sources'/(k+'-metadata.json')).read_text());r={c:'UNVERIFIED' for c in cols};r.update(work_id=k,title=d['title'][0],year=str(d['published']['date-parts'][0][0]),venue=d['container-title'][0],status='PEER-REVIEWED; METADATA-ONLY SCREEN',identifier=d['DOI'],source_url='https://doi.org/'+d['DOI'],granularity='Layerpipeline+SLOstageallocation' if k=='planck2024' else 'Layerallocation+deadlinepreemptivescheduling',verification_gaps='Crossref title, complete authors, venue and DOI verified. Full text inaccessible or not audited; technical claims UNVERIFIED.');rows.append(r)
with (p/'related-work-table.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
# Parse balanced-brace BibTeX entries, deduplicate by verified DOI or title.
entries=[];ids=set();keys=set()
for fn in ['edge-references.bib','migration-references.bib','venue-references.bib','root-references.bib']:
 text=(p/fn).read_text()
 for m in re.finditer(r'@\w+\s*\{',text):
  i=m.end();depth=1
  while i<len(text) and depth:
   if text[i]=='{':depth+=1
   if text[i]=='}':depth-=1
   i+=1
  e=text[m.start():i];key=re.match(r'@\w+\s*\{\s*([^,]+)',e)[1]
  doi=re.search(r'\bdoi\s*=\s*\{([^}]+)',e,re.I);tit=re.search(r'\btitle\s*=\s*\{([^\n]+)',e,re.I)
  identity=doi[1].lower() if doi else re.sub(r'[^a-z0-9]','',tit[1].lower()) if tit else key
  if identity in ids:continue
  if key in keys:raise ValueError('duplicate key '+key)
  ids.add(identity);keys.add(key);entries.append(e)
(p/'references-new.bib').write_text('% Audit2026-10-06. Primary metadata verified where asserted; unresolved fields omitted or marked UNVERIFIED.\n% Sources/technical verification levels are detailed in related-work-table.csv and venue-requirements.md.\n\n'+'\n\n'.join(entries)+'\n')
claims=p/'claims-open-vs-taken.md';s=claims.read_text().replace('https://arxiv.org/search/?query=DynoPipe&searchtype=title','https://yanyinglin.github.io/assets/pdf/DynoPipe-ISCA26.pdf');claims.write_text(s)
print('FINAL',len(rows),'CSV rows;',len(entries),'BibTeX entries; unique work IDs and keys verified')
