"""Laboratory 8: Grafana and Prometheus screenshots for the time windows of the experiments (Playwright + Edge).
Grafana is opened as the anonymous Viewer (no password is typed).

  python scripts/lab8/grafana_shots.py load        # dashboards for load-before and load-after
  python scripts/lab8/grafana_shots.py rebalance   # dashboards for the shard moves
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_shots import Browser

E = Path(__file__).resolve().parents[2] / 'evidence/lab8'


def window(tag, before=10_000, after=15_000):
    ev = json.loads((E / f'{tag}-events.json').read_text(encoding='utf-8'))
    return ev['startMs'] - before, ev['endMs'] + after


def load(b):
    for tag in ('load-before', 'load-after', 'locations-before', 'locations-after'):
        if not (E / f'{tag}-events.json').exists(): continue
        start, end = window(tag)
        b.grafana('traveler-api', f'g-api-{tag}', start, end)
        b.grafana('traveler-postgres', f'g-pg-{tag}', start, end)
    if (E / 'load-before-events.json').exists() and (E / 'locations-after-events.json').exists():
        start, _ = window('load-before'); _, end = window('locations-after')
        b.grafana('traveler-postgres', 'g-pg-all-bench', start, end)
        b.grafana('traveler-api', 'g-api-all-bench', start, end)


def rebalance(b):
    start, end = window('rebalance')
    b.grafana('traveler-api', 'g-api-rebalance', start, end)
    b.grafana('traveler-postgres', 'g-pg-rebalance', start, end)


if __name__ == '__main__':
    b = Browser()
    try:
        {'load': load, 'rebalance': rebalance}[sys.argv[1]](b)
    finally:
        b.close()
