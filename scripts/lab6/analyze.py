"""Analysis of the laboratory 6 k6 runs: summaries, steady plateaus, rebalance timeline, charts."""
import gzip, json, math, re, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / 'evidence/lab6'; FIG = E / 'figures'; FIG.mkdir(exist_ok=True)
plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 12})
CONFIGS = {'baseline': '1 БД, 1 API', 'baseline-2api': '1 БД, 2 API', 'sharded-naive': '16 БД 4×0,5 CPU, 1 API (перша версія)', 'sharded-equal': '16 БД 4×0,5 CPU, 1 API', 'sharded-scaled': '16 БД 4×2 CPU, 1 API', 'sharded-scaled-2api': '16 БД 4×2 CPU, 2 API'}
PLATEAUS = [(15, 35, 25), (55, 75, 50), (95, 115, 100), (135, 155, 200)]


def summary(tag, test):
    m = json.loads((E / tag / f'{test}-summary.json').read_text())['metrics']
    d = m['http_req_duration']['values']
    return {'avg': d['avg'], 'med': d['med'], 'p95': d['p(95)'], 'p99': d.get('p(99)'), 'max': d['max'],
            'rps': m['http_reqs']['values']['rate'], 'reqs': m['http_reqs']['values']['count'],
            'failed': m['http_req_failed']['values']['rate'], 'checks': m['checks']['values']['rate'],
            'thresholds': {k: [ok['ok'] for ok in v.get('thresholds', {}).values()] for k, v in m.items() if v.get('thresholds')}}


def points(tag):
    with gzip.open(E / f'{tag}-raw.json.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            p = json.loads(line)
            if p.get('type') == 'Point' and p['metric'] in ('http_req_duration', 'http_req_failed'):
                yield p['metric'], datetime.fromisoformat(p['data']['time'].replace('Z', '+00:00')).timestamp(), p['data']['value'], p['data'].get('tags', {})


def p95(values):
    v = sorted(values); return v[min(len(v) - 1, math.ceil(0.95 * len(v)) - 1)] if v else float('nan')


def plateaus(tag):
    start = re.search(r'K6_SCENARIO_START=(\S+)', (E / f'{tag}-console.txt').read_text(encoding='utf-8'))
    t0 = datetime.fromisoformat(start.group(1).replace('Z', '+00:00')).timestamp()
    buckets = defaultdict(list)
    for metric, t, value, tags in points(tag):
        if metric != 'http_req_duration' or tags.get('phase') == 'setup': continue
        for a, b, vu in PLATEAUS:
            if a <= t - t0 < b: buckets[vu].append(value)
    return {vu: {'p95': p95(buckets[vu]), 'rps': len(buckets[vu]) / (b - a)} for a, b, vu in PLATEAUS}


def rebalance(tag):
    ev = json.loads((E / f'{tag}-events.json').read_text())
    t0 = ev['k6StartEpoch']
    per = defaultdict(lambda: defaultdict(list)); fails = defaultdict(lambda: defaultdict(int)); total = defaultdict(lambda: [0, 0])
    worst = defaultdict(float)
    for metric, t, value, tags in points(tag):
        s = int(t - t0); group = tags.get('shard', 'other')
        if metric == 'http_req_duration':
            per[group][s].append(value); worst[group] = max(worst[group], value)
        else:
            fails[group][s] += int(value); total[group][0] += int(value); total[group][1] += 1
    groups = {g: {'requests': total[g][1], 'failed': total[g][0], 'max': worst[g],
                  'p95': p95([v for vals in per[g].values() for v in vals])} for g in per}
    return {'moves': ev['moves'], 'groups': groups,
            'series': {g: {s: {'max': max(v), 'p95': p95(v), 'n': len(v)} for s, v in sorted(per[g].items())} for g in per}}


def chart_load(res):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.6))
    vus = [25, 50, 100, 200]
    for key, label in CONFIGS.items():
        pl = res[key]['plateaus']
        a.plot(vus, [pl[v]['p95'] for v in vus], marker='o', label=label)
        b.plot(vus, [pl[v]['rps'] for v in vus], marker='o', label=label)
    a.set(xlabel='VU на плато', ylabel='p95, мс', title='p95 затримки на сталих плато', xscale='log'); a.set_xticks(vus, vus)
    b.set(xlabel='VU на плато', ylabel='запитів за секунду', title='Пропускна здатність', xscale='log'); b.set_xticks(vus, vus)
    for x in (a, b): x.grid(alpha=.3)
    a.legend(fontsize=9); fig.tight_layout(); fig.savefig(FIG / 'load-plateaus.png', dpi=170); plt.close(fig)


def chart_read(res):
    fig, ax = plt.subplots(figsize=(11, 4.4))
    labels = list(CONFIGS.values()); x = range(len(labels))
    rps = [res[k]['read']['median_rps'] for k in CONFIGS]; p = [res[k]['read']['median_p95'] for k in CONFIGS]
    bars = ax.bar(x, rps, color=['#7f7f7f', '#b0b0b0', '#c9a227', '#1f77b4', '#2ca02c', '#17803d'])
    ax.set_xticks(list(x), [l.replace(', ', ',' + chr(10), 1) for l in labels], fontsize=10); ax.set_ylabel('запитів за секунду (медіана 3 запусків)')
    for b_, r_, p_ in zip(bars, rps, p): ax.text(b_.get_x() + b_.get_width() / 2, r_, f'{r_:.0f} req/s\np95 {p_:.0f} мс', ha='center', va='bottom')
    ax.set_ylim(0, max(rps) * 1.25); ax.grid(axis='y', alpha=.3); ax.set_title('Read: 200 VU, список планів і деталі плану')
    fig.tight_layout(); fig.savefig(FIG / 'read-comparison.png', dpi=170); plt.close(fig)


def chart_distribution():
    d = json.loads((E / 'distribution.json').read_text())
    fig, ax = plt.subplots(figsize=(10, 3.6))
    colors = {'postgres_00': '#1f77b4', 'postgres_01': '#ff7f0e', 'postgres_02': '#2ca02c', 'postgres_03': '#d62728'}
    for r in d['rows']: ax.bar(r['database'], r['plans'], color=colors[r['server']])
    for host, c in colors.items(): ax.bar(0, 0, color=c, label=host)
    ax.axhline(2000 / 16, color='k', ls='--', lw=1, label='рівномірно: 125')
    ax.set_ylabel('планів подорожей'); ax.legend(ncol=5, fontsize=10, loc='lower center', bbox_to_anchor=(.5, 1.0)); ax.grid(axis='y', alpha=.3)
    fig.tight_layout(); fig.savefig(FIG / 'distribution.png', dpi=170); plt.close(fig)


def chart_rebalance(tag, data, title):
    fig, ax = plt.subplots(figsize=(11, 4))
    names = {'3': 'шард 3 (db_3)', '7': 'шард 7 (db_7)', 'other': 'інші 14 шардів', 'new': 'нові плани'}
    for g in ('other', '3', '7'):
        s = data['series'][g]; xs = sorted(s)
        ax.plot(xs, [s[x]['max'] for x in xs], label=f'max, {names[g]}', lw=1.3)
    for m in data['moves']:
        ax.axvspan(m['startOffsetSeconds'], m['endOffsetSeconds'], color='orange', alpha=.25)
        ax.text(m['startOffsetSeconds'], ax.get_ylim()[1] * .92, f" {m['database']}→{m['target']}", fontsize=10)
    ax.set(xlabel='секунди від старту k6', ylabel='максимальна затримка за секунду, мс', title=title)
    ax.grid(alpha=.3); ax.legend(loc='upper right', fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / f'{tag}-timeline.png', dpi=170); plt.close(fig)


if __name__ == '__main__':
    res = {}
    for key in CONFIGS:
        reads = [summary(f'{key}-read-{i}', 'read') for i in (1, 2, 3)]
        res[key] = {'load': summary(f'{key}-load', 'load'), 'plateaus': plateaus(f'{key}-load'),
                    'read': {'runs': reads, 'median_rps': statistics.median(r['rps'] for r in reads),
                             'median_p95': statistics.median(r['p95'] for r in reads)}}
    for tag in ('rebalance-file', 'rebalance-registry'):
        res[tag] = rebalance(tag); res[tag]['summary'] = summary(tag, 'rebalance')
    (E / 'analysis.json').write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')
    chart_load(res); chart_read(res); chart_distribution()
    chart_rebalance('rebalance-file', res['rebalance-file'], 'Переміщення db_3 і db_7 під навантаженням (mapping.json)')
    chart_rebalance('rebalance-registry', res['rebalance-registry'], 'Переміщення db_3 і db_7 під навантаженням (реєстр)')
    for k in CONFIGS: print(k, {x: round(y, 2) for x, y in res[k]['load'].items() if isinstance(y, float)}, res[k]['read']['median_rps'])
    for t in ('rebalance-file', 'rebalance-registry'): print(t, json.dumps(res[t]['groups']))
