"""Laboratory 6 orchestration: sharded TravelerAPI, CLI tools, measurements.
Only the traveler_lab6* Compose projects are created or reset."""
import argparse, datetime, hashlib, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/lab6'; OUT.mkdir(parents=True, exist_ok=True)
COMPOSE = ['docker', 'compose', '-f', 'docker-compose.lab6.yml']
NODES = ['postgres_00', 'postgres_01', 'postgres_02', 'postgres_03']
SHARDS = '0123456789abcdef'


def load_env():
    values = {}
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1); values[k] = v
    return values


def environment(mode, **extra):
    env = os.environ.copy(); env.update(load_env())
    env.update(COMPOSE_PROJECT_NAME='traveler_lab6' if mode == 'sharded' else 'traveler_lab6_baseline',
               COMPOSE_PROFILES='sharded' if mode == 'sharded' else 'baseline',
               DOCKER_SUBNET='172.29.60.0/24' if mode == 'sharded' else '172.29.61.0/24')
    state = ROOT / '.runtime/lab6/state.json'
    if state.exists(): env.update(json.loads(state.read_text()).get('env', {}))
    if env.get('LB') == '1': env['COMPOSE_PROFILES'] += ',lb' if mode == 'sharded' else ',baseline-lb'
    env.update(extra)
    return env


def run(args, mode, check=True, **kw):
    return subprocess.run(args, cwd=ROOT, env=environment(mode), text=True, encoding='utf-8', check=check, **kw)


def dc(mode, *args, **kw): return run([*COMPOSE, *args], mode, **kw)


def save(name, value):
    (OUT / name).write_text(value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    return value


def psql(mode, service, db, query, tuples=True):
    args = ['exec', '-T', service, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', load_env()['DB_ADMIN'], '-d', db]
    if tuples: args += ['-At']
    out = dc(mode, *args, input=query, capture_output=True).stdout
    return out.strip() if tuples else out.rstrip() + chr(10)


def tool(*args, check=True):
    """Run a CLI tool inside the backend network (tools service)."""
    r = dc('sharded', '--profile', 'tools', 'run', '--rm', '-T', 'tools', *args, capture_output=True, check=False)
    text = (r.stdout or '') + '\n'.join(l for l in (r.stderr or '').splitlines() if not l.startswith(' Container'))
    if check and r.returncode: print(text); raise RuntimeError(f'tool failed: {args}')
    return r.returncode, text


def up(mode, cpus='0.5', memory='256M', source='file', fresh=True, lb=False):
    other = 'baseline' if mode == 'sharded' else 'sharded'
    dc(other, 'stop', capture_output=True, check=False)
    state = ROOT / '.runtime/lab6/state.json'; state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({'mode': mode, 'env': {'SHARD_CPUS': cpus, 'SHARD_MEMORY': memory, 'MAPPING_SOURCE': source, 'LB': '1' if lb else '0'}}))
    if fresh:
        dc(mode, 'down', '-v', '--remove-orphans', capture_output=True, check=False)
        if mode == 'sharded': shutil.copy(ROOT / 'config/mapping.json', ROOT / '.runtime/lab6/mapping.json')
    dc(mode, 'up', '-d', '--wait', '--build')
    save(f'{mode}-compose-ps.txt', dc(mode, 'ps', '--format', 'table {{.Name}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}', capture_output=True).stdout)
    print('READY', mode, cpus, memory, source, flush=True)


def lab2_plan_ids():
    ids = []
    for i in range(1, 2001):
        h = hashlib.md5(f'lab2-plan-{i}'.encode()).hexdigest()
        ids.append(f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}')
    return [{'id': x} for x in sorted(ids)]


def seed(mode):
    if mode == 'sharded':
        code, text = tool('tools/shard-exec.js', '/sql/000_seed_lab2_dataset.sql')
        save('seed-shard-exec.txt', text)
    else:
        env = load_env(); db = env['DB_NAME']
        src = (ROOT / 'sql/000_seed_lab2_dataset.sql').read_text(encoding='utf-8')
        # Same rows without the shard filter: one database keeps everything.
        body = '\n'.join('WHERE true;' if l.startswith('WHERE right(') else l for l in src.splitlines())
        psql(mode, 'postgres', db, body)
    (ROOT / 'tests/performance-tests/seed.json').write_text(json.dumps(lab2_plan_ids()), encoding='utf-8')
    print('SEEDED', mode, json.dumps(distribution(mode)['total'] if mode == 'sharded' else baseline_counts()), flush=True)


def baseline_counts():
    db = load_env()['DB_NAME']
    return json.loads(psql('baseline', 'postgres', db, "SELECT json_build_object('plans',(SELECT count(*) FROM travel_plans),'locations',(SELECT count(*) FROM locations))"))


def mapping():
    return json.loads((ROOT / '.runtime/lab6/mapping.json').read_text())


def distribution(mode='sharded', name=None):
    m = mapping(); rows = []
    for s in SHARDS:
        host = m['shards'][s]['host']
        r = psql(mode, host, f'db_{s}', "SELECT count(*) FROM travel_plans; SELECT count(*) FROM locations;").split('\n')
        rows.append({'shard': s, 'server': host, 'database': f'db_{s}', 'plans': int(r[0]), 'locations': int(r[1])})
    result = {'mappingVersion': m['version'], 'rows': rows,
              'total': {'plans': sum(r['plans'] for r in rows), 'locations': sum(r['locations'] for r in rows)}}
    if name: save(name, result)
    return result


def hurl(mode, tag):
    net = environment(mode)['COMPOSE_PROJECT_NAME'] + '_backend'
    host = 'web' if mode == 'sharded' else 'web_baseline'
    r = subprocess.run(['docker', 'run', '--rm', '--network', net, '-v', str(ROOT / 'tests') + ':/tests:ro',
                        'ghcr.io/orange-opensource/hurl:8.0.0', '--test', '--color', '--variable', f'host=http://{host}:4567',
                        '/tests/crud.hurl', '/tests/validation.hurl', '/tests/management.hurl', '/tests/race-conditions.hurl'],
                       capture_output=True, text=True, encoding='utf-8')
    save(f'{tag}-hurl.txt', r.stdout + r.stderr); save(f'{tag}-hurl-exit.json', {'exitCode': r.returncode})
    print('HURL', tag, r.returncode, flush=True)
    return r.returncode


def concurrency(tag):
    r = subprocess.run(['node', '--test', 'tests/concurrency.test.js'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    save(f'{tag}-concurrency.txt', r.stdout + r.stderr)
    print('CONCURRENCY', tag, r.returncode, flush=True)
    return r.returncode


def stats_loop(mode, proc, path):
    with path.open('w', encoding='utf-8') as stats:
        while proc.poll() is None:
            ids = dc(mode, 'ps', '-q', capture_output=True).stdout.split()
            r = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{json .}}', *ids], capture_output=True, text=True)
            for row in r.stdout.splitlines(): stats.write(json.dumps({'at': time.time(), **json.loads(row)}) + '\n')
            stats.flush(); time.sleep(3)


def k6_path():
    return ROOT.parent / '.tools/k6/k6-v2.3.0-windows-amd64/k6.exe'


def benchmark(mode, test, tag):
    seed(mode)
    result_dir = f'evidence/lab6/{tag}'; (ROOT / result_dir).mkdir(exist_ok=True)
    env = environment(mode, RESULT_DIR=result_dir)
    env['API_URL'] = 'http://127.0.0.1:4570' if env.get('LB') == '1' else 'http://127.0.0.1:4567'
    script = ROOT / f'tests/performance-tests/{test}-test.js'
    args = [str(k6_path()), 'run', '--out', f'json=evidence/lab6/{tag}-raw.json.gz', str(script)]
    meta = {'mode': mode, 'scenario': test, 'tag': tag, 'startedUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'shardCpus': env.get('SHARD_CPUS'), 'shardMemory': env.get('SHARD_MEMORY'), 'apiUrl': env['API_URL'],
            'scenarioSHA256': hashlib.sha256(script.read_bytes()).hexdigest()}
    start = time.monotonic()
    with (OUT / f'{tag}-console.txt').open('w', encoding='utf-8') as out:
        proc = subprocess.Popen(args, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
        stats_loop(mode, proc, OUT / f'{tag}-docker-stats.jsonl')
        meta.update(exitCode=proc.wait(), elapsedSeconds=time.monotonic() - start)
    save(f'{tag}-run.json', meta)
    values = json.loads((ROOT / result_dir / f'{test}-summary.json').read_text())['metrics']
    print('BENCHMARK', tag, 'exit', meta['exitCode'], 'p95', values['http_req_duration']['values']['p(95)'],
          'req/s', values['http_reqs']['values']['rate'], flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action'); p.add_argument('mode', nargs='?', default='sharded')
    p.add_argument('--cpus', default='0.5'); p.add_argument('--memory', default='256M')
    p.add_argument('--source', default='file'); p.add_argument('--test', default='load'); p.add_argument('--tag')
    p.add_argument('--keep', action='store_true')
    p.add_argument('--lb', action='store_true')
    a = p.parse_args()
    if a.action == 'up': up(a.mode, a.cpus, a.memory, a.source, not a.keep, a.lb)
    elif a.action == 'seed': seed(a.mode)
    elif a.action == 'distribution': print(json.dumps(distribution(a.mode, a.tag and a.tag + '.json'), indent=1))
    elif a.action == 'hurl': sys.exit(hurl(a.mode, a.tag or a.mode))
    elif a.action == 'concurrency': sys.exit(concurrency(a.tag or a.mode))
    elif a.action == 'benchmark': benchmark(a.mode, a.test, a.tag)
    elif a.action == 'stop': dc(a.mode, 'stop')
    else: raise SystemExit('unknown action')
