"""Cross-check genuine k6 aggregates, raw-sample analyses, duration and database cleanup."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent.parent/'tests/performance-tests/results'
def read(name):return json.loads((R/name).read_text(encoding='utf-8-sig'))
for name in ('load','stress','spike','endurance'):
    summary=read(f'{name}-summary.json');analysis=read(f'{name}-analysis.json')
    reqs=summary['metrics']['http_reqs']['values']['count']
    measured=sum(v['requests'] for v in analysis['phases'].values())
    assert measured+1==reqs,(name,'sample count mismatch',measured,reqs)
    failures=sum(v['failures'] for v in analysis['phases'].values())
    assert abs(failures/reqs-summary['metrics']['http_req_failed']['values']['rate'])<1e-12
    check=read(f'{name}-data-check.json')
    assert (check['plans'],check['locations'],check['temporary_plans'],check['orphan_locations'])==(2000,6000,0,0),(name,check)
    run=read(f'{name}-run.json')
    expected=99 if name in ('stress','spike') else 0
    assert run['exitCode']==expected,(name,'unexpected k6 exit',run['exitCode'])
    print(f'{name}: {reqs} requests; samples and aggregates agree; database clean; exit {expected}')
endurance=read('endurance-analysis.json');run=read('endurance-run.json')
assert len(endurance['steady_minutes'])==30
assert run['elapsedSeconds']>=1860
assert endurance['stable_plateaus']['steady']['target_vus']==25
assert read('ci-proof.json')['conclusion']=='success'
print('Endurance includes all 30 steady minutes and at least 31 minutes total; CI smoke succeeded')
