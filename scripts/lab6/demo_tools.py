"""Evidence for the shard-exec CLI: dry run, commit, failure on one shard, refusal."""
import json, sys, urllib.request
sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
import lab6
from lab6 import tool, save, psql, mapping, SHARDS


def state():
    m = mapping(); rows = []
    for s in SHARDS:
        host = m['shards'][s]['host']
        out = psql('sharded', host, f'db_{s}', """SELECT coalesce((SELECT string_agg(version, ',' ORDER BY version) FROM schema_migrations), '-');
          SELECT count(*) FROM pg_constraint WHERE conname = 'budget_limit';
          SELECT count(*) FROM pg_indexes WHERE indexname = 'idx_plans_public';
          SELECT count(*) FROM travel_plans WHERE budget > 5000;""")
        v, c, i, b = out.split('\n')
        rows.append(f'{s} | {host} | db_{s} | migrations={v:<7} | budget_limit={c} | idx_plans_public={i} | plans>5000={b}')
    return '\n'.join(rows)


def api(method, path, body=None):
    req = urllib.request.Request('http://127.0.0.1:4567' + path, method=method,
                                 data=json.dumps(body).encode() if body else None, headers={'content-type': 'application/json'})
    with urllib.request.urlopen(req) as r: return json.loads(r.read() or b'null')


if __name__ == '__main__':
    # schema_migrations does not exist yet, so the state check starts after 010.
    code, text = tool('tools/shard-exec.js', '/sql/010_schema_migrations.sql', '--dry-run', check=False)
    save('tools-01-dry-run.txt', f'$ node tools/shard-exec.js /sql/010_schema_migrations.sql --dry-run\n{text}\nexit code {code}\n')
    code, text = tool('tools/shard-exec.js', '/sql/010_schema_migrations.sql', '--show-prepared', check=False)
    save('tools-02-commit.txt', f'$ node tools/shard-exec.js /sql/010_schema_migrations.sql --show-prepared\n{text}\nexit code {code}\n')
    save('tools-03-state-after-commit.txt', state())
    plan = api('POST', '/api/travel-plans', {'title': 'Expensive trip for the failing migration', 'budget': 9000, 'currency': 'EUR'})
    save('tools-04-expensive-plan.json', {'id': plan['id'], 'shard': plan['id'][-1], 'budget': plan['budget'],
                                          'server': mapping()['shards'][plan['id'][-1]]['host']})
    code, text = tool('tools/shard-exec.js', '/sql/020_budget_limit_fails.sql', check=False)
    save('tools-05-failure.txt', f'$ node tools/shard-exec.js /sql/020_budget_limit_fails.sql\n{text}\nexit code {code}\n')
    save('tools-06-state-after-failure.txt', state())
    code, text = tool('tools/shard-exec.js', '/sql/030_own_transaction.sql', check=False)
    save('tools-07-refused.txt', f'$ node tools/shard-exec.js /sql/030_own_transaction.sql\n{text}\nexit code {code}\n')
    code, text = tool('tools/shard-exec.js', '/sql/040_check_shard_keys.sql', check=False)
    save('tools-08-invariant.txt', f'$ node tools/shard-exec.js /sql/040_check_shard_keys.sql\n{text}\nexit code {code}\n')
    api('DELETE', f"/api/travel-plans/{plan['id']}")
    print('DEMO TOOLS OK')
