"""The merged list of the API must equal the global order computed from all 16 databases."""
import json, sys, urllib.request
sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from lab6 import psql, mapping, save, SHARDS

rows = []
m = mapping()
for s in SHARDS:
    out = psql('sharded', m['shards'][s]['host'], f'db_{s}',
               "SELECT id || '|' || to_char(created_at AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS') FROM travel_plans")
    rows += [tuple(line.split('|')) for line in out.splitlines() if line]
# created_at DESC, id ASC
rows.sort(key=lambda r: r[0]); rows.sort(key=lambda r: r[1], reverse=True)
expected = [r[0] for r in rows]
report, ok = [], True
for page in range(1, 11):
    with urllib.request.urlopen(f'http://127.0.0.1:4567/api/travel-plans?page={page}&limit=20') as r:
        got = [p['id'] for p in json.loads(r.read())]
    same = got == expected[(page - 1) * 20: page * 20]
    ok &= same
    shards = ''.join(sorted({i[-1] for i in got}))
    report.append(f'page {page:>2}: {len(got)} plans from shards [{shards}] -> {"MATCH" if same else "DIFFERENT"}')
report.append(f'total plans in 16 databases: {len(expected)}; pages 1-10 equal to global ORDER BY created_at DESC, id: {ok}')
save('list-order-check.txt', '\n'.join(report))
print('\n'.join(report))
sys.exit(0 if ok else 1)
