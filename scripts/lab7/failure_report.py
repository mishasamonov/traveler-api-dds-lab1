"""Laboratory 7: alert timeline and Prometheus numbers of the last failure experiment, plus its screenshots."""
import json, sys, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_shots import Browser

E = Path(__file__).resolve().parents[2] / 'evidence/lab7'
ev = json.loads((E / 'failure-events.json').read_text())
stop = next(e['ms'] for e in ev['events'] if 'stop' in e)
start = next(e['ms'] for e in ev['events'] if 'start' in e and 'ms' in e)


def prom(path, **params):
    return json.load(urllib.request.urlopen(f'http://127.0.0.1:9090/api/v1/{path}?' + urllib.parse.urlencode(params)))['data']


res = prom('query_range', query='max by (alertname, alertstate, server, api) (ALERTS)', start=stop / 1000 - 10, end=start / 1000 + 120, step=5)['result']
rows = []
for r in res:
    m = r['metric']; ts = [float(v[0]) for v in r['values']]
    rows.append({'alert': m['alertname'], 'state': m['alertstate'], 'target': m.get('api') or m.get('server') or '',
                 'fromSeconds': round(min(ts) - stop / 1000), 'toSeconds': round(max(ts) - stop / 1000)})
rows.sort(key=lambda r: (r['fromSeconds'], r['alert']))
(E / 'failure-alert-timeline.json').write_text(json.dumps({'stopMs': stop, 'startMs': start, 'rows': rows}, indent=2))
d = (start - stop) // 1000
before = prom('query', query='sum(rate(http_request_duration_seconds_count{route!~"/health|/metrics"}[20s]))', time=stop / 1000 - 2)['result']
q = lambda expr: prom('query', query=expr, time=start / 1000)['result']
stats = {'outageSeconds': d, 'rpsBefore': float(before[0]['value'][1]),
         'errorsByServerCode': [{**r['metric'], 'count': round(float(r['value'][1]))} for r in q(f'sum by (server, code) (increase(db_errors_total[{d}s])) > 0')],
         'httpByStatus': [{**r['metric'], 'count': round(float(r['value'][1]))} for r in q(f'sum by (status) (increase(http_request_duration_seconds_count{{route!~"/health|/metrics"}}[{d}s])) > 0')]}
(E / 'failure-prometheus.json').write_text(json.dumps(stats, indent=2))
print(json.dumps(stats, indent=1)); [print(r) for r in rows]
b = Browser()
try:
    b.grafana('traveler-api', 'g-api-failure', stop - 40000, start + 70000)
    b.grafana('traveler-api', 'g-panel-errors-failure', stop - 40000, start + 70000, panel=20, height=760, width=1500)
    b.grafana('traveler-api', 'g-panel-alerts-failure', stop - 40000, start + 70000, panel=8, height=560, width=1500)
finally:
    b.close()
