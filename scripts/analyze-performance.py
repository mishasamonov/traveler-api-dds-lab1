"""Reproduce tables and figures from genuine timestamped k6 output, no server dependency."""
import argparse, csv, gzip, json, math, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

def percentile(values, p):
    a = sorted(values)
    if not a: return None
    i = (len(a)-1)*p/100
    return a[math.floor(i)]*(math.ceil(i)-i) + a[math.ceil(i)]*(i-math.floor(i)) if i % 1 else a[int(i)]

def stats(v, errors):
    return dict(requests=len(v),avg_ms=statistics.fmean(v) if v else None,p95_ms=percentile(v,95),
                p99_ms=percentile(v,99),max_ms=max(v) if v else None,failures=sum(errors),
                failure_rate=statistics.fmean(errors) if errors else 0)

def analyze(folder, name):
    phase_duration,phase_failed = defaultdict(list),defaultdict(list)
    windows_d,windows_e = defaultdict(list),defaultdict(list)
    phases_time = {}
    origin = None
    statuses = defaultdict(int)
    with gzip.open(folder/f'{name}-raw.json.gz','rt',encoding='utf-8') as stream:
        for line in stream:
            r=json.loads(line)
            if r['type']!='Point': continue
            metric=r['metric']; d=r['data']; tags=d.get('tags',{})
            if tags.get('phase')=='setup': continue
            if metric not in ('http_req_duration','http_req_failed'): continue
            t=datetime.fromisoformat(d['time']).timestamp()
            if origin is None: origin=t
            elapsed=t-origin; window=int(elapsed//5)*5; phase=tags.get('phase','all')
            phases_time.setdefault(phase,elapsed)
            if metric=='http_req_duration':
                phase_duration[phase].append(d['value']);windows_d[window].append(d['value'])
                statuses[tags.get('status','unknown')]+=1
            else:
                phase_failed[phase].append(d['value']);windows_e[window].append(d['value'])
    result={'test':name,'time_origin_unix':origin,'origin_note':'First measured HTTP completion, after setup',
        'phases':{p:{**stats(v,phase_failed[p]),'first_sample_s':phases_time[p]} for p,v in phase_duration.items()},
        'windows_5s':[{'start_s':w,**stats(v,windows_e[w])} for w,v in sorted(windows_d.items())], 'http_statuses':dict(statuses)}
    # Minute comparisons for the 30-minute plateau are based on steady-tagged requests.
    if name=='endurance':
        steady=phases_time.get('steady',30)
        minute_d,minute_e=defaultdict(list),defaultdict(list)
        with gzip.open(folder/f'{name}-raw.json.gz','rt',encoding='utf-8') as stream:
            for line in stream:
                r=json.loads(line)
                if r['type']!='Point' or r['metric'] not in ('http_req_duration','http_req_failed'): continue
                d=r['data']
                if d.get('tags',{}).get('phase')!='steady': continue
                minute=int((datetime.fromisoformat(d['time']).timestamp()-origin-steady)//60)+1
                if 1<=minute<=30:
                    (minute_d if r['metric']=='http_req_duration' else minute_e)[minute].append(d['value'])
        result['steady_minutes']={str(m):stats(v,minute_e[m]) for m,v in sorted(minute_d.items())}
    (folder/f'{name}-analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(name, json.dumps(result['phases'],ensure_ascii=False))
    return result

def plot(folder, results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
    for result in results:
        fig,axes=plt.subplots(3,1,figsize=(9,7.4),sharex=True,layout='constrained')
        rows=result['windows_5s'];x=[r['start_s']/60 for r in rows]
        axes[0].plot(x,[r['p95_ms'] for r in rows],color='#215b91',lw=1.7,label='p95 HTTP')
        axes[0].axhline(500,color='#b74c36',ls='--',lw=1,label='SLO 500 ms');axes[0].set_ylabel('p95, ms');axes[0].legend(loc='upper left')
        axes[1].plot(x,[r['requests']/5 for r in rows],color='#26725a',lw=1.5);axes[1].set_ylabel('Requests/s')
        axes[2].plot(x,[r['failure_rate']*100 for r in rows],color='#b74c36',lw=1.5);axes[2].set_ylabel('HTTP errors, %');axes[2].set_xlabel('Elapsed time, minutes')
        for ax in axes: ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
        fig.suptitle(f'TravelerAPI {result["test"]} - native Windows baseline',fontsize=15)
        fig.savefig(folder/f'{result["test"]}-chart.png',dpi=180);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('tests',nargs='*',default=['load','stress','spike','endurance']);p.add_argument('--folder',default='tests/performance-tests/results');p.add_argument('--plot',action='store_true');a=p.parse_args()
    folder=Path(a.folder);results=[analyze(folder,n) for n in a.tests]
    if a.plot:plot(folder,results)
