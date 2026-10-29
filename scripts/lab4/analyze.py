"""Rebuild the report's numbers and plot from retained raw measurements."""
import gzip,json,re,statistics,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
R=Path(__file__).resolve().parents[2]/'evidence/lab4'
MODES=['baseline','logical','physical','sync','pgcat']
def percentile(v,p=95):
    v=sorted(v);i=(len(v)-1)*p/100;a=int(i);b=math.ceil(i)
    return v[a]*(b-i)+v[b]*(i-a) if a!=b else v[a]
def summary(mode,scenario='load',tag=None):
    return json.loads((R/(tag or f'{mode}-{scenario}')/(scenario+'-summary.json')).read_text())['metrics']
def analyze(mode):
    log=(R/f'{mode}-load-console.txt').read_text(encoding='utf-8')
    start=datetime.fromisoformat(re.search(r'K6_SCENARIO_START=([0-9T:.Z-]+)',log)[1]).timestamp()
    windows=[(15,35,25),(55,75,50),(95,115,100),(135,155,200)]
    durations=defaultdict(list);errors=defaultdict(list)
    with gzip.open(R/f'{mode}-load-raw.json.gz','rt',encoding='utf-8') as f:
        for line in f:
            if not any(x in line for x in ['"http_req_duration"','"http_req_failed"']):continue
            r=json.loads(line)
            if r['type']!='Point':continue
            d=r['data'];t=datetime.fromisoformat(d['time']).timestamp()-start
            for a,b,vu in windows:
                if a<=t<b:
                    (durations if r['metric']=='http_req_duration' else errors)[vu].append(d['value']);break
    result={str(vu):{'vus':vu,'from_s':a,'to_s':b,'requests':len(durations[vu]),
        'avg_ms':statistics.fmean(durations[vu]),'p95_ms':percentile(durations[vu]),
        'rps':len(durations[vu])/(b-a),'failure_rate':statistics.fmean(errors[vu])} for a,b,vu in windows}
    (R/f'{mode}-load-analysis.json').write_text(json.dumps(result,indent=2))
    return result
def main():
    plateaus={mode:analyze(mode) for mode in MODES}
    main={}
    for mode in MODES:
        m=summary(mode)
        main[mode]={'requests':m['http_reqs']['values']['count'],'rps':m['http_reqs']['values']['rate'],
          'avg_ms':m['http_req_duration']['values']['avg'],'p95_ms':m['http_req_duration']['values']['p(95)'],
          'failure_rate':m['http_req_failed']['values']['rate'],
          'checks_rate':m['checks']['values']['rate'],
          'exitCode':json.loads((R/f'{mode}-load-run.json').read_text())['exitCode']}
    reads={}
    for mode in ['two','pgcat']:
        values=[]
        for i in range(1,4):
            m=summary(mode,'read',f'{mode}-read-{i}')
            values.append({'rps':m['http_reqs']['values']['rate'],
                'p95_ms':m['http_req_duration']['values']['p(95)'],
                'failure_rate':m['http_req_failed']['values']['rate']})
        reads[mode]={'runs':values,'median_rps':statistics.median(v['rps'] for v in values),
          'median_p95_ms':statistics.median(v['p95_ms'] for v in values)}
    result={'load':main,'plateaus':plateaus,'reads':reads,
       'read_rps_change_percent':100*(reads['pgcat']['median_rps']/reads['two']['median_rps']-1),
       'read_p95_change_percent':100*(reads['pgcat']['median_p95_ms']/reads['two']['median_p95_ms']-1)}
    (R/'analysis.json').write_text(json.dumps(result,indent=2))
    text='ORIGINAL LAB 2 MIXED LOAD - WHOLE RUN\n'
    text+='mode       requests   avg_ms   p95_ms   req/s    HTTP errors\n'
    for mode,m in main.items():text+=f"{mode:10} {m['requests']:8} {m['avg_ms']:8.2f} {m['p95_ms']:8.2f} {m['rps']:8.2f} {100*m['failure_rate']:8.2f}%\n"
    text+='\nREAD-ONLY 200 VU - THREE 45 SECOND RUNS\n'
    for mode,m in reads.items():text+=f"{mode:10} median {m['median_rps']:.2f} req/s; median p95 {m['median_p95_ms']:.2f} ms\n"
    text+=f"PgCat throughput change: {result['read_rps_change_percent']:+.2f}%\n"
    (R/'comparison.txt').write_text(text);print(text)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('C:/Windows/Fonts/times.ttf')
    plt.rcParams.update({'font.family':'Times New Roman','font.size':14})
    fig,axes=plt.subplots(2,1,figsize=(9,6.7),sharex=True,layout='constrained')
    colors=['#333333','#186c9c','#348450','#b45b29','#7f4a9e']
    for mode,color in zip(MODES,colors):
        x=[25,50,100,200]
        axes[0].plot(x,[plateaus[mode][str(v)]['p95_ms'] for v in x],marker='o',label=mode,color=color)
        axes[1].plot(x,[plateaus[mode][str(v)]['rps'] for v in x],marker='o',color=color)
    axes[0].axhline(500,color='#c64949',ls='--',lw=1,label='SLO 500 ms')
    axes[0].set_ylabel('p95, ms');axes[0].legend(ncol=3,fontsize=12)
    axes[1].set_ylabel('Requests/s');axes[1].set_xlabel('Concurrent users');axes[1].set_xticks([25,50,100,200])
    for ax in axes:ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.savefig(R/'load-comparison.png',dpi=200);plt.close(fig)
if __name__=='__main__':main()
