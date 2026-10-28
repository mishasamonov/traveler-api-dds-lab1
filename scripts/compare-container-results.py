"""Compare genuine lab 2 baseline and Docker runs, keeping whole-run and plateau metrics separate."""
import json,statistics,re,csv,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
BASE=ROOT/'tests/performance-tests/results'
NEW=ROOT/'tests/performance-tests/results-docker'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def memory(s):
 v,u=re.match(r'([\d.]+)\s*([A-Za-z]+)',s.strip()).groups()
 return float(v)*{'B':1/1024**2,'kB':1000/1024**2,'KB':1000/1024**2,'KiB':1/1024,'MB':1000**2/1024**2,'MiB':1,'GB':1000**3/1024**2,'GiB':1024}[u]
def stats(name):
 rows=[json.loads(x) for x in (NEW/f'{name}-docker-stats.jsonl').read_text().splitlines()]
 out={}
 for service in ('web','postgres'):
  r=[x for x in rows if f'-{service}-' in x['Name']]
  out[service]={'samples':len(r),'cpu_mean_pct':statistics.fmean(float(x['CPUPerc'].rstrip('%')) for x in r),
   'cpu_peak_pct':max(float(x['CPUPerc'].rstrip('%')) for x in r),
   'memory_peak_mib':max(memory(x['MemUsage'].split('/')[0]) for x in r),
   'memory_median_mib':statistics.median(memory(x['MemUsage'].split('/')[0]) for x in r)}
 return out
def main():
 result={'whole_runs':[],'plateaus':{},'resources':{},'data_checks':{},'limitations':[
  'Historical native Windows and Docker Desktop Linux runs; one run per scenario.',
  'OS, virtualization, network/storage and resource limits differ; not an isolated Docker overhead.',
  'Docker memory usage is not Windows private bytes; these are not directly comparable.']}
 for name in ('smoke','load','stress','spike','endurance'):
  a=load(BASE/f'{name}-summary.json')['metrics'];b=load(NEW/f'{name}-summary.json')['metrics']
  def values(m):return {'avg_ms':m['http_req_duration']['values']['avg'],'p95_ms':m['http_req_duration']['values']['p(95)'],
   'requests':m['http_reqs']['values']['count'],'rps':m['http_reqs']['values']['rate'],
   'failure_rate':m['http_req_failed']['values']['rate'],'http_failures':m['http_req_failed']['values']['passes'],
   'failed_checks':m['checks']['values']['fails']}
  av,bv=values(a),values(b)
  result['whole_runs'].append({'test':name,'baseline':av,'docker':bv,'p95_change_pct':(bv['p95_ms']/av['p95_ms']-1)*100})
  result['resources'][name]=stats(name)
  result['data_checks'][name]=load(NEW/f'{name}-data-check.json')
  if name!='smoke':
   ba=load(BASE/f'{name}-analysis.json');ne=load(NEW/f'{name}-analysis.json')
   result['plateaus'][name]={key:{'baseline':v,'docker':ne['stable_plateaus'][key]} for key,v in ba['stable_plateaus'].items()}
 (NEW/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 with (NEW/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(['test','baseline_avg_ms','docker_avg_ms','baseline_p95_ms','docker_p95_ms','p95_change_pct','baseline_error_rate','docker_error_rate'])
  for x in result['whole_runs']:w.writerow([x['test'],x['baseline']['avg_ms'],x['docker']['avg_ms'],x['baseline']['p95_ms'],x['docker']['p95_ms'],x['p95_change_pct'],x['baseline']['failure_rate'],x['docker']['failure_rate']])
 print(json.dumps(result['whole_runs'],indent=2))
if __name__=='__main__':main()
