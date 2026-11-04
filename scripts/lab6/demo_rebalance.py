"""Move shards while k6 drives both API instances; keep every output as evidence.
python scripts/lab6/demo_rebalance.py <tag> db_3:postgres_03:30 db_7:postgres_02:60 [--drop-source]"""
import datetime, json, subprocess, sys, time
sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from lab6 import ROOT, OUT, tool, save, dc, environment, k6_path, distribution, stats_loop
import threading

tag = sys.argv[1]
moves = [m.split(':') for m in sys.argv[2:] if not m.startswith('--')]
drop = '--drop-source' in sys.argv
since = datetime.datetime.now(datetime.timezone.utc).isoformat()
result_dir = f'evidence/lab6/{tag}'; (ROOT / result_dir).mkdir(exist_ok=True)
env = environment('sharded', RESULT_DIR=result_dir, DURATION='100s')
_, before = tool('tools/rebalance.js', 'status')
save(f'{tag}-status-before.txt', before)
args = [str(k6_path()), 'run', '--out', f'json=evidence/lab6/{tag}-raw.json.gz', 'tests/performance-tests/rebalance-test.js']
k6_start = time.time()
out = (OUT / f'{tag}-console.txt').open('w', encoding='utf-8')
proc = subprocess.Popen(args, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
threading.Thread(target=stats_loop, args=('sharded', proc, OUT / f'{tag}-docker-stats.jsonl'), daemon=True).start()
events = []
for db, target, at in moves:
    while time.time() - k6_start < float(at): time.sleep(0.2)
    started = time.time()
    code, text = tool('tools/rebalance.js', 'move', db, target, *(['--drop-source'] if drop else []), check=False)
    events.append({'database': db, 'target': target, 'startOffsetSeconds': round(started - k6_start, 3),
                   'endOffsetSeconds': round(time.time() - k6_start, 3), 'exitCode': code})
    save(f'{tag}-move-{db}.txt', f'$ node tools/rebalance.js move {db} {target}{" --drop-source" if drop else ""}\n{text}')
    print('MOVED', db, target, code, flush=True)
proc.wait(); out.close()
save(f'{tag}-events.json', {'k6StartEpoch': k6_start, 'moves': events})
_, after = tool('tools/rebalance.js', 'status')
save(f'{tag}-status-after.txt', after)
logs = ''
for service in ('web', 'web2'):
    r = dc('sharded', 'logs', '--no-color', '--no-log-prefix', '--since', since, service, capture_output=True)
    logs += f'===== {service} =====\n' + '\n'.join(l for l in r.stdout.splitlines() if 'mapping_loaded' in l or 'shard_retry' in l or 'Error' in l) + '\n'
save(f'{tag}-api-logs.txt', logs)
distribution('sharded', f'{tag}-distribution.json')
from lab6 import psql
save(f'{tag}-registry.txt', psql('sharded', 'postgres_02', 'shard_registry', """SELECT version, updated_at FROM registry_meta;
  SELECT shard, host, database, updated_at FROM shard_map WHERE shard IN ('3', '7') ORDER BY shard;
  SELECT shard, from_host, to_host, version, lock_ms, moved_at FROM shard_moves ORDER BY id;""", tuples=False))
summary = json.loads((ROOT / result_dir / 'rebalance-summary.json').read_text())['metrics']
print('REBALANCE', tag, 'k6 exit', proc.returncode, 'failed', summary['http_req_failed']['values']['rate'], flush=True)
