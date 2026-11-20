"""Laboratory 8: terminal and editor screenshots from saved evidence and repository files."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import terminal, code, read, lines_of, E

DC = 'docker compose -f docker-compose.lab6.yml -f docker-compose.monitoring.yml -f docker-compose.lab8.yml'


def exists(name): return (E / name).exists()


def cmd_and_body(name):
    text = read(name)
    if text.startswith('$ '):
        first, rest = text.split('\n', 1)
        return first[2:], rest
    return None, text


# --- code -------------------------------------------------------------------
a, b = lines_of('db/migrations/002_plan_documents.sql', '-- Laboratory 8', 'CREATE OR REPLACE FUNCTION plan_document_valid')
code('c01-location-valid', 'db/migrations/002_plan_documents.sql', a, b - 2)
a, b = lines_of('db/migrations/002_plan_documents.sql', 'CREATE OR REPLACE FUNCTION plan_document_valid', 'CREATE TABLE IF NOT EXISTS plan_documents')
code('c02-plan-valid', 'db/migrations/002_plan_documents.sql', a, b - 2)
a, b = lines_of('db/migrations/002_plan_documents.sql', 'CREATE TABLE IF NOT EXISTS plan_documents', 'CREATE OR REPLACE VIEW travel_plans_view')
code('c03-table-indexes', 'db/migrations/002_plan_documents.sql', a, b - 5)
a, b = lines_of('db/migrations/002_plan_documents.sql', '-- Relational views over the documents', '-- Audit of storage migrations')
code('c04-views', 'db/migrations/002_plan_documents.sql', a, b - 2)
a, b = lines_of('sql/100_migrate_to_jsonb.sql', '-- Laboratory 8', '-- 4. Verification')
code('c05-migrate-backfill', 'sql/100_migrate_to_jsonb.sql', a, b - 2)
a, b = lines_of('sql/100_migrate_to_jsonb.sql', '-- 4. Verification', '-- 7. One result row')
code('c06-migrate-verify', 'sql/100_migrate_to_jsonb.sql', a, b - 2)
code('c07-rollback', 'sql/190_rollback_to_relational.sql')
code('c08-drop-legacy', 'sql/110_drop_legacy.sql')
code('c09-documents-js', 'src/documents.js')
a, b = lines_of('src/app.js', "// One indexed read instead of two queries", "app.put('/api/travel-plans/:id'")
code('c10-app-get', 'src/app.js', a - 4, b - 2)
a, b = lines_of('src/app.js', '// One atomic UPDATE: the row lock', '// Read - change - write')
code('c11-app-post-location', 'src/app.js', a, b - 2)
a, b = lines_of('src/app.js', '// Read - change - write', '// Remove one element of the array')
code('c12-app-put-location', 'src/app.js', a, b - 2)
a, b = lines_of('src/app.js', '// Remove one element of the array', 'app.use((error')
code('c13-app-delete-location', 'src/app.js', a, b - 2)
a, b = lines_of('tools/shard-exec.js', '// Apply one DDL/DML script', "const { SHARDS, readMapping")
code('c14-shard-exec-head', 'tools/shard-exec.js', a, b)
a, b = lines_of('tools/rebalance.js', '// Two storage layouts', 'async function registryVersion')
code('c15-rebalance-layouts', 'tools/rebalance.js', a, b - 2)
code('c16-compose-lab8', 'docker-compose.lab8.yml')
code('c17-locations-test', 'tests/performance-tests/locations-test.js', 1, 46)
a, b = lines_of('scripts/lab8/ci-init.js', '// CI of laboratory 8', "(async () => {")
code('c18-ci-init', 'scripts/lab8/ci-init.js', a, b - 2)
a, b = lines_of('.github/workflows/tests.yml', 'name: TravelerAPI tests', 'node scripts/lab8/ci-init.js')
code('c19-workflow', '.github/workflows/tests.yml', b - 14, b + 1)
code('c20-old-schema', 'db/migrations/001_schema.sql', 1, 35)
code('c21-sql-120', 'sql/120_plpgsql_document_check.sql')
code('c22-check-v1', 'evidence/lab8/002_plan_documents_v1.sql', 40, 62)

# --- terminal ---------------------------------------------------------------
if exists('compose-ps.txt'):
    terminal('t01-compose-ps', [('python scripts/lab8/lab8.py up', 'READY traveler_lab8 API traveler-api:lab7'),
                                (f'{DC} ps', read('compose-ps.txt'))], width=1300)
if exists('seed-shard-exec.txt'):
    terminal('t02-seed', [('python scripts/lab8/lab8.py seed   # tools/shard-exec.js /sql/000_seed_lab2_dataset.sql', read('seed-shard-exec.txt'))], width=1300)
for tag in ('hurl-before', 'hurl-after', 'hurl-final'):
    if exists(f'{tag}.txt'):
        terminal(f't-{tag}', [(f'python scripts/lab8/lab8.py hurl --tag {tag}   # 5 Hurl files + tests/concurrency.test.js', read(f'{tag}.txt')),
                              ('node --test tests/concurrency.test.js', '\n'.join(l for l in read(f'{tag}-concurrency.txt').splitlines()
                                                                         if l.startswith(('ok ', 'not ok', '# tests', '# pass', '# fail'))))], width=1300)
for tag in ('sql', 'plpgsql'):
    if exists(f'check-cost-{tag}.txt'):
        terminal(f't-check-cost-{tag}', [(f'python scripts/lab8/lab8.py check-cost --tag {tag}', read(f'check-cost-{tag}.txt'))], width=1500)
for name in ('migrate-dry-run', 'migrate-shard-exec', 'rollback-dry-run', 'contract-shard-exec', 'rebalance-move-db_3', 'rebalance-move-db_7',
             'plpgsql-shard-exec', 'rebalance-failed-log', 'search-path-before-fix', 'search-path-fix-shard-exec'):
    if exists(f'{name}.txt'):
        c, body = cmd_and_body(f'{name}.txt')
        terminal(f't-{name}', [(c, body)], width=1700)
if exists('migrate-log.txt'):
    terminal('t-migrate-log', [('python scripts/lab8/lab8.py migrate', read('migrate-log.txt'))], width=1500)
for name in ('document-sample', 'document-view', 'document-table', 'storage-migrations', 'tables-after'):
    if exists(f'{name}.txt'):
        c, body = cmd_and_body(f'{name}.txt')
        terminal(f't-{name}', [(c, body)], width=1500)
if exists('check-demo.txt'):
    terminal('t-check-demo', [('python scripts/lab8/lab8.py check-demo   # psql -a -d db_0: every change in its own transaction, then ROLLBACK',
                               read('check-demo.txt'))], title='psql db_0', width=1500)
if exists('dump-before.json') and exists('dump-after.json'):
    b, a = json.loads(read('dump-before.json')), json.loads(read('dump-after.json'))
    lines = []
    for x in (b, a):
        lines.append(f"{x['tag']:<6}  API {x['api']:<17}  responses {x['responses']}  md5 {x['md5']}")
    lines.append('identical: ' + str(b['md5'] == a['md5']).lower())
    diff = sum(1 for l1, l2 in zip(read('dump-before.txt').splitlines(), read('dump-after.txt').splitlines()) if l1 != l2)
    lines.append(f'responses that differ: {diff}')
    terminal('t-dump', [('python scripts/lab8/lab8.py dump --tag before   # relational API, right before the migration', ''),
                        ('python scripts/lab8/lab8.py dump --tag after    # JSONB API, right after the migration', '\n'.join(lines))], width=1300)
for name in ('bench-sizes', 'wal', 'explain-get-relational', 'explain-get-jsonb', 'explain-location-relational', 'explain-location-gin',
             'explain-location-seqscan', 'explain-list-relational', 'explain-list-jsonb', 'wal-explain-relational', 'wal-explain-jsonb'):
    if exists(f'{name}.txt'):
        terminal(f't-{name}', [(None, read(f'{name}.txt'))], title='psql jsonb_bench', width=1500)


def k6_summary(tag):
    lines = read(f'{tag}-console.txt').splitlines()
    first = next(i for i, l in enumerate(lines) if l.startswith('k6 ') and l.endswith('TEST'))
    body = '\n'.join(l for l in lines[first:] if l.strip() and not l.startswith(('running (', 'default ', 'traffic ', 'rebalance ', 'keys ', 'locations ')))
    return lines[0][2:], body


for tag in ('load-before', 'load-after', 'key-before', 'key-after', 'locations-before', 'locations-after-v1', 'locations-after', 'rebalance'):
    if exists(f'{tag}-console.txt'):
        command, summary = k6_summary(tag)
        terminal(f't-k6-{tag}', [(command, summary)], width=1500)


def statements(tag, top=9):
    rows = json.loads(read(f'{tag}-statements.json'))
    total = sum(r['calls'] for r in rows if r['query'] != 'SELECT $1')
    out = [f"{'calls':>8} {'avg ms':>8} {'WAL MB':>8}  query"]
    for r in rows[:top]:
        q = r['query'] if len(r['query']) < 118 else r['query'][:115] + '...'
        out.append(f"{r['calls']:>8} {r['ms'] / max(r['calls'], 1):>8.3f} {r['wal'] / 1048576:>8.1f}  {q}")
    out.append(f'{total:>8}  statements of the API role on db_0..db_f in total')
    return '\n'.join(out)


for tag in ('locations-before', 'locations-after-v1', 'locations-after', 'load-before', 'load-after'):
    if exists(f'{tag}-statements.json'):
        terminal(f't-pgss-{tag}', [(None, statements(tag))], title=f'pg_stat_statements: {tag} (4 servers, saved by lab8.py bench)', width=1750)
if exists('git-log.txt'):
    terminal('t-git', [('git log --oneline -6', read('git-log.txt')), ('git push -u origin lab8-jsonb', read('git-push.txt'))])
