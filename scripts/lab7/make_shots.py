"""Laboratory 7: terminal and editor screenshots from saved evidence and repository files."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import terminal, code, read, lines_of, E

DC = 'docker compose -f docker-compose.lab6.yml -f docker-compose.monitoring.yml'


def body(name):
    text = read(name)
    return text.split('\n', 1)[1] if text.startswith('$ ') else text


def exists(name): return (E / name).exists()


# --- code -------------------------------------------------------------------
code('c01-metrics-definitions', 'src/metrics.js', 1, 54)
code('c02-metrics-pool-middleware', 'src/metrics.js', 56, 103)
a, b = lines_of('src/shards.js', 'async function withShard', 'metrics.setPoolSource'); code('c03-shards-observe', 'src/shards.js', a - 3, b + 4)
code('c04-app-metrics', 'src/app.js', 1, 17)
code('c05-compose-exporters', 'docker-compose.monitoring.yml', 1, 59)
a, _ = lines_of('docker-compose.monitoring.yml', '  prometheus:'); code('c06-compose-prometheus-grafana', 'docker-compose.monitoring.yml', a, a + 60)
a, b = lines_of('db/shard/500_init_node.sh', '# Laboratory 7', 'fi'); code('c07-init-monitor-role', 'db/shard/500_init_node.sh', a, b)
a, b = lines_of('db/shard/500_init_node.sh', 'cat > "$PGDATA/pg_hba.conf"', 'EOF'); code('c08-pg-hba', 'db/shard/500_init_node.sh', a, b)
code('c09-prometheus-yml', 'monitoring/prometheus/prometheus.yml')
code('c10-alerts-api', 'monitoring/prometheus/alerts.yml', 1, 76)
a, _ = lines_of('monitoring/prometheus/alerts.yml', '  - name: postgres'); code('c11-alerts-postgres', 'monitoring/prometheus/alerts.yml', a)
code('c12-grafana-datasource', 'monitoring/grafana/provisioning/datasources/prometheus.yml')
code('c13-grafana-provider', 'monitoring/grafana/provisioning/dashboards/traveler.yml')
a, b = lines_of('scripts/lab7/dashboards.py', "api.row('Шарди: 16 віртуальних вузлів')", "api.add(timeseries('p95 запиту до БД"); code('c14-dashboards-shards', 'scripts/lab7/dashboards.py', a, b - 1)
code('c15-metrics-hurl', 'tests/metrics.hurl')
code('c16-shards-test', 'tests/performance-tests/shards-test.js', 1, 46)

# --- terminal ---------------------------------------------------------------
if exists('compose-ps.txt'):
    terminal('t01-compose-ps', [('python scripts/lab7/lab7.py up', 'READY traveler_lab7'), (f'{DC} ps', read('compose-ps.txt'))], width=1500)
if exists('seed-shard-exec.txt'):
    terminal('t02-seed', [('python scripts/lab7/lab7.py seed   # tools/shard-exec.js /sql/000_seed_lab2_dataset.sql', read('seed-shard-exec.txt'))])
if exists('metrics-sample.txt'):
    terminal('t03-metrics', [('curl -s http://127.0.0.1:4567/metrics | grep -E "' + read('metrics-sample-filter.txt').strip() + '"', read('metrics-sample.txt'))], width=1500)
if exists('hurl.txt'):
    terminal('t04-hurl', [('python scripts/lab7/lab7.py hurl   # crud, validation, management, race-conditions, metrics', read('hurl.txt'))])
if exists('security.txt'):
    terminal('t05-security', [('psql   # role lab7_monitor, its privileges and pg_hba.conf on postgres_00', read('security.txt'))], width=1400)


def k6_summary(tag):
    lines = read(f'{tag}-console.txt').splitlines()
    first = next(i for i, l in enumerate(lines) if l.startswith('k6 ') and l.endswith('TEST'))
    body = '\n'.join(l for l in lines[first:] if l.strip() and not l.startswith(('running (', 'default ', 'traffic ', 'rebalance ')))
    return lines[0][2:], body


for tag in ('load', 'hotspot', 'failure', 'rebalance'):
    if exists(f'{tag}-console.txt'):
        command, summary = k6_summary(tag)
        terminal(f't-k6-{tag}', [(command, summary)], width=1500)
if exists('created-at.txt'):
    terminal('t-created-at', [('python scripts/lab7/lab7.py created-at   # max(created_at) of the seed in every shard, sorted', read('created-at.txt'))])
if exists('promtool.txt'):
    terminal('t06-promtool', [(None, read('promtool.txt'))])
if exists('promtool-broken.txt'):
    terminal('t07-promtool-broken', [(None, read('promtool-broken.txt'))], width=1500)
if exists('hurl-after.txt'):
    terminal('t-hurl-after', [('python scripts/lab7/lab7.py hurl --tag hurl-after   # mapping v4 after the moves', read('hurl-after.txt'))])
if exists('rebalance-first-move-db_3.txt'):
    text = read('rebalance-first-move-db_3.txt')
    terminal('t-move-first-db_3', [(text.split('\n', 1)[0][2:], text.split('\n', 1)[1])], width=1500)
if exists('rebalance-retry-db_5.txt'):
    terminal('t-retry-db_5', [(None, read('rebalance-retry-db_5.txt'))], width=1500)
for db in ('db_3', 'db_7'):
    if exists(f'rebalance-move-{db}.txt'):
        text = read(f'rebalance-move-{db}.txt')
        terminal(f't-move-{db}', [(text.split('\n', 1)[0][2:], text.split('\n', 1)[1])], width=1400)
if exists('failure-log.txt'):
    terminal('t-failure-log', [('python scripts/lab7/lab7.py failure', read('failure-log.txt'))], width=1400)
if exists('git-log.txt'):
    terminal('t-git', [('git log --oneline -6', read('git-log.txt')), ('git push -u origin lab7-monitoring', read('git-push.txt'))])
