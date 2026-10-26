"""Reproduce tables and figures from genuine timestamped k6 output, no server dependency."""
import argparse, ast, csv, gzip, json, math, re, statistics
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
    samples, vus = [], []
    with gzip.open(folder/f'{name}-raw.json.gz','rt',encoding='utf-8') as stream:
        for line in stream:
            if not any(m in line for m in ('http_req_duration','http_req_failed','"vus"')): continue
            r=json.loads(line)
            if r['type']!='Point': continue
            metric=r['metric']; d=r['data']; tags=d.get('tags',{})
            if metric=='vus':
                vus.append((datetime.fromisoformat(d['time']).timestamp(), d['value']))
                continue
            if tags.get('phase')=='setup': continue
            if metric not in ('http_req_duration','http_req_failed'): continue
            t=datetime.fromisoformat(d['time']).timestamp()
            if origin is None: origin=t
            elapsed=t-origin; window=int(elapsed//5)*5; phase=tags.get('phase','all')
            samples.append((t,metric,d['value']))
            phases_time.setdefault(phase,elapsed)
            if metric=='http_req_duration':
                phase_duration[phase].append(d['value']);windows_d[window].append(d['value'])
                statuses[tags.get('status','unknown')]+=1
            else:
                phase_failed[phase].append(d['value']);windows_e[window].append(d['value'])
    result={'test':name,'time_origin_unix':origin,'origin_note':'First measured HTTP completion, after setup',
        'phases':{p:{**stats(v,phase_failed[p]),'first_sample_s':phases_time[p]} for p,v in phase_duration.items()},
        'windows_5s':[{'start_s':w,**stats(v,windows_e[w])} for w,v in sorted(windows_d.items())], 'http_statuses':dict(statuses)}
    # Stable plateau comparisons use completion timestamps and omit 5 seconds
    # at each edge, rather than assigning a slow journey to its starting phase.
    start=None;anchor=None
    for suffix in ('stderr.txt','console.txt'):
        log=(folder/f'{name}-{suffix}')
        if log.exists():
            anchor=re.search(r'K6_SCENARIO_START=([0-9T:.Z-]+)',log.read_text(encoding='utf-8-sig'))
            if anchor: start=datetime.fromisoformat(anchor[1]).timestamp();break
    if start is None: start=vus[0][0]-1 if vus else origin
    result['scenario_start_unix']=start
    result['scenario_start_method']='Logged scenario start' if anchor else 'First 1-second VU sample minus 1 second (approximate)'
    result['vus']=[{'elapsed_s':t-start,'value':v} for t,v in vus]
    source=(Path(__file__).parent.parent/'tests/performance-tests/utils/workload.js').read_text(encoding='utf-8')
    profile=ast.literal_eval(re.search(r'\b'+name+r':\s*(\[\[.*?\]\])',source)[1])
    schedule=[];elapsed=0;previous=0
    for seconds,target,label in profile:
        if target>0 and target==previous and seconds>=30:
            # Downscaling permits old iterations to drain for 30 seconds.
            # Compare settled recovery only after that explicit grace period.
            trim=35 if label=='recovery' else 5
            schedule.append((elapsed+trim,elapsed+seconds-5,label,target))
        elapsed+=seconds;previous=target
    stable_d,stable_e=defaultdict(list),defaultdict(list)
    for t,metric,value in samples:
        for a,b,label,_ in schedule:
            if a<=t-start<b:
                (stable_d if metric=='http_req_duration' else stable_e)[label].append(value);break
    result['stable_plateaus']={label:{'target_vus':target,'from_s':a,'to_s':b,
        **stats(stable_d[label],stable_e[label]),'rps':len(stable_d[label])/(b-a)} for a,b,label,target in schedule}
    result['plateau_note']='HTTP completion times; 5 seconds excluded at each edge; recovery also excludes the configured 30-second graceful drain'
    if name in ('stress','spike'):
        down_end=0
        for seconds,_,label in profile:
            down_end+=seconds
            if label in ('down','fall'):break
        windows=result['windows_5s'];recovered=None
        for i in range(len(windows)-2):
            time=windows[i]['start_s']+origin-start
            if time<down_end:continue
            if all(r['p95_ms']<500 and r['failure_rate']<.01 for r in windows[i:i+3]):
                recovered=max(0,time-down_end);break
        result['recovery']={'seconds_after_nominal_down_end':recovered,'resolution_seconds':5,
            'rule':'First of three consecutive 5-second windows with p95 < 500 ms and failures < 1%',
            'nominal_down_end_s':down_end,'graceful_ramp_down_s':30}
    resource_file=folder/f'{name}-resources.csv'
    if resource_file.exists():
        rows=list(csv.DictReader(resource_file.open(encoding='utf-8-sig',newline='')))
        run_file=folder/f'{name}-run.json'
        api_pid=json.loads(run_file.read_text(encoding='utf-8-sig')).get('apiPid',16544) if run_file.exists() else 16544
        memory=[{'elapsed_s':datetime.fromisoformat(r['timestamp']).timestamp()-start,
                 'private_mb':float(r['PrivateMemorySize64'])/1024**2,
                 'cpu_seconds':float(r['CPU'].replace(',','.'))}
                for r in rows if r['Id']==str(api_pid)]
        result['api_resources']=memory
        if memory:
            result['api_memory']={'first_mb':memory[0]['private_mb'],'last_mb':memory[-1]['private_mb'],
                'peak_mb':max(r['private_mb'] for r in memory),
                'first_5min_median_mb':statistics.median(r['private_mb'] for r in memory if (30<=r['elapsed_s']<330 if name=='endurance' else r['elapsed_s']<330)),
                'last_5min_median_mb':statistics.median(r['private_mb'] for r in memory if (1530<=r['elapsed_s']<1830 if name=='endurance' else r['elapsed_s']>max(x['elapsed_s'] for x in memory)-300))}
    # Minute comparisons for the 30-minute plateau are based on steady-tagged requests.
    if name=='endurance':
        steady=30
        minute_d,minute_e=defaultdict(list),defaultdict(list)
        with gzip.open(folder/f'{name}-raw.json.gz','rt',encoding='utf-8') as stream:
            for line in stream:
                if 'http_req_duration' not in line and 'http_req_failed' not in line: continue
                r=json.loads(line)
                if r['type']!='Point' or r['metric'] not in ('http_req_duration','http_req_failed'): continue
                d=r['data']
                minute=int((datetime.fromisoformat(d['time']).timestamp()-start-steady)//60)+1
                if 1<=minute<=30:
                    (minute_d if r['metric']=='http_req_duration' else minute_e)[minute].append(d['value'])
        result['steady_minutes']={str(m):stats(v,minute_e[m]) for m,v in sorted(minute_d.items())}
        for key,indices in [('first_5min',range(1,6)),('last_5min',range(26,31))]:
            result[key]=stats([v for m in indices for v in minute_d[m]],[v for m in indices for v in minute_e[m]])
    (folder/f'{name}-analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(name, json.dumps(result['stable_plateaus'],ensure_ascii=False))
    return result

def plot(folder, results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
    for result in results:
        fig,axes=plt.subplots(3,1,figsize=(9,6.3),sharex=True,layout='constrained')
        rows=result['windows_5s'];offset=result['time_origin_unix']-result['scenario_start_unix']
        x=[(r['start_s']+offset)/60 for r in rows]
        if result['test']=='endurance':
            duration_ax=axes[0];rate_ax=axes[1]
            memory=result.get('api_resources',[])
            axes[2].plot([r['elapsed_s']/60 for r in memory],[r['private_mb'] for r in memory],color='#70519a',lw=1.4)
            axes[2].set_ylabel('API private MB')
            duration_ax.text(.99,.9,'SLO: 500 ms',transform=duration_ax.transAxes,ha='right',fontsize=10)
        else:
            duration_ax=axes[1];rate_ax=axes[2]
            vu=result['vus'];axes[0].step([r['elapsed_s']/60 for r in vu],[r['value'] for r in vu],where='post',color='#70519a',lw=1.4)
            axes[0].set_ylabel('Active VUs')
            duration_ax.axhline(500,color='#b74c36',ls='--',lw=1,label='SLO 500 ms')
        duration_ax.plot(x,[r['p95_ms'] for r in rows],color='#215b91',lw=1.7,label='p95 HTTP')
        duration_ax.set_ylabel('p95, ms');duration_ax.legend(loc='upper left',fontsize=9)
        rate_ax.plot(x,[r['requests']/5 for r in rows],color='#26725a',lw=1.5);rate_ax.set_ylabel('Requests/s')
        axes[2].set_xlabel('Elapsed time, minutes')
        for ax in axes: ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
        fig.suptitle(f'TravelerAPI {result["test"]} - native Windows baseline',fontsize=15)
        fig.savefig(folder/f'{result["test"]}-chart.png',dpi=180,bbox_inches='tight',pad_inches=.12);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('tests',nargs='*',default=['load','stress','spike','endurance']);p.add_argument('--folder',default='tests/performance-tests/results');p.add_argument('--plot',action='store_true');a=p.parse_args()
    folder=Path(a.folder);results=[analyze(folder,n) for n in a.tests]
    if a.plot:plot(folder,results)
