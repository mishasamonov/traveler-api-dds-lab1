"""Publication figures from timestamped HTTP metrics, with identical time axes."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
EXTRA=ROOT.parent/'.tools/python-extra'
if EXTRA.exists():sys.path.insert(0,str(EXTRA))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT.parent/'.tools/lab3/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
font=Path('C:/Windows/Fonts/times.ttf')
if font.exists():font_manager.fontManager.addfont(str(font))
plt.rcParams.update({'font.family':'Times New Roman','font.size':14})
R=ROOT/'tests/performance-tests/results-docker'
B=ROOT/'tests/performance-tests/results'
for name in ('load','stress','spike','endurance'):
 if not (R/f'{name}-analysis.json').exists():continue
 a=json.loads((B/f'{name}-analysis.json').read_text(encoding='utf-8-sig'))
 b=json.loads((R/f'{name}-analysis.json').read_text(encoding='utf-8-sig'))
 fig,axes=plt.subplots(2,1,figsize=(9,4.8),sharex=True,gridspec_kw={'height_ratios':[2,1]})
 fig.subplots_adjust(left=.11,right=.98,top=.89,bottom=.14,hspace=.2)
 for result,label,color in [(a,'Лаб 2 без Docker','#a05b20'),(b,'Лаб 3 Docker','#215b91')]:
  x=[(r['start_s']+result['time_origin_unix']-result['scenario_start_unix'])/60 for r in result['windows_5s']]
  axes[0].plot(x,[r['p95_ms'] for r in result['windows_5s']],label=label,color=color,lw=1.6)
 if name=='endurance':
  axes[0].text(.99,.9,'Поріг SLO 500 мс',transform=axes[0].transAxes,ha='right',fontsize=12)
 else:axes[0].axhline(500,color='#b23a36',ls='--',lw=.9,label='Поріг 500 мс')
 axes[0].set_ylabel('p95, мс');axes[0].legend(fontsize=12,loc='upper left',ncol=2)
 x=[(r['start_s']+b['time_origin_unix']-b['scenario_start_unix'])/60 for r in b['windows_5s']]
 axes[1].plot(x,[r['failure_rate']*100 for r in b['windows_5s']],color='#8e3436',lw=1.4)
 axes[1].set_ylim(0,max(1,max(r['failure_rate']*100 for r in b['windows_5s'])*1.12))
 axes[1].set_ylabel('Помилки, %');axes[1].set_xlabel('Час від початку сценарію, хв')
 for ax in axes:ax.grid(alpha=.22);ax.spines[['top','right']].set_visible(False)
 fig.suptitle(f'TravelerAPI {name}  порівняння однакових сценаріїв',fontsize=15)
 fig.savefig(R/f'{name}-comparison.png',dpi=200);plt.close(fig)
 print(name)
