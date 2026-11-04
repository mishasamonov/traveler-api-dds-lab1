"""Build every report screenshot from saved evidence and repository files."""
import json, sys
sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from screenshots import terminal, code, read, lines_of, E

DC = 'docker compose -f docker-compose.lab6.yml'
TOOLS = f'{DC} --profile tools run --rm tools'


def body(name):  # saved tool outputs start with "$ command"
    text = read(name)
    return text.split('\n', 1)[1] if text.startswith('$ ') else text


def j(name): return json.dumps(json.loads(read(name)), indent=2, ensure_ascii=False)


# --- code -------------------------------------------------------------------
code('c01-mapping', 'config/mapping.json', 1, 22)
a, _ = lines_of('docker-compose.lab6.yml', 'x-shard: &shard'); code('c02-compose', 'docker-compose.lab6.yml', a, a + 33)
a, _ = lines_of('docker-compose.lab6.yml', '  postgres_00:'); code('c03-compose-services', 'docker-compose.lab6.yml', a, a + 30)
a, b = lines_of('db/shard/500_init_node.sh', 'prepare_database() {', 'done'); code('c04-init-node', 'db/shard/500_init_node.sh', a, b)
a, b = lines_of('db/shard/500_init_node.sh', 'if [ "$REGISTRY_ROLE" = publisher ]', 'fi'); code('c05-init-registry', 'db/shard/500_init_node.sh', a, b)
code('c06-shards-head', 'src/shards.js', 1, 31)
a, b = lines_of('src/shards.js', 'function poolFor(target)', 'const query ='); code('c07-pools', 'src/shards.js', a, b)
a, b = lines_of('src/app.js', "app.post('/api/travel-plans',", '});'); code('c08-app-post', 'src/app.js', a, b)
a, b = lines_of('src/app.js', "app.post('/api/travel-plans/:id/locations'", '// Co-location'); code('c09-app-location', 'src/app.js', a, b + 4)
a, b = lines_of('src/app.js', "app.get('/api/travel-plans',", '});'); code('c10-app-list', 'src/app.js', a, b)
code('c11-seed-sql', 'sql/000_seed_lab2_dataset.sql')
a, b = lines_of('tools/shard-exec.js', '  // Phase 1: connect', "      outcome = 'ROLLBACK on all 16: PREPARE failed';"); code('c12-shard-exec', 'tools/shard-exec.js', a, b)
a, b = lines_of('tools/shard-exec.js', '      // Phase 3:', '    }\n'.strip() or '}'); code('c13-shard-exec-commit', 'tools/shard-exec.js', a, a + 9)
code('c14-sql-failure', 'sql/020_budget_limit_fails.sql')
a, b = lines_of('tools/rebalance.js', "await step('1. create target", "await step('2."); code('c15-rebalance-1', 'tools/rebalance.js', a, b - 2)
a, b = lines_of('tools/rebalance.js', "await step('3. LOCK", "await step('4."); code('c16-rebalance-3', 'tools/rebalance.js', a, b - 2)
a, b = lines_of('tools/rebalance.js', "await step('4. promote", "if (options.dropSource)"); code('c17-rebalance-4-6', 'tools/rebalance.js', a, b - 2)
a, b = lines_of('src/shards.js', 'async function withShard', 'const query ='); code('c18-with-shard', 'src/shards.js', a - 3, b)
code('c19-registry-sql', 'db/shard/registry.sql')
a, b = lines_of('src/shards.js', 'async function readRegistry()', 'async function load()'); code('c20-read-registry', 'src/shards.js', a, b + 3)

# --- terminal ---------------------------------------------------------------
terminal('t01-compose-ps', [(f'{DC} ps', read('topology-compose-ps.txt'))])
terminal('t02-databases', [('python scripts/lab6/topology.py   # pg_database + pg_settings on every service', read('topology-databases.txt'))])
terminal('t03-health', [('curl http://127.0.0.1:4567/health', read('topology-health-4567.json')),
                        ('curl http://127.0.0.1:4568/health', read('topology-health-4568.json'))])
terminal('t04-seed', [(f'{TOOLS} tools/shard-exec.js /sql/000_seed_lab2_dataset.sql', read('seed-shard-exec.txt'))])
d = json.loads(read('distribution.json'))
dist = '\n'.join(f"db_{r['shard']}  {r['server']}  plans={r['plans']:>4}  locations={r['locations']:>4}" for r in d['rows'])
terminal('t05-distribution', [('python scripts/lab6/lab6.py distribution sharded', dist + f"\nTOTAL plans={d['total']['plans']} locations={d['total']['locations']} (mapping v{d['mappingVersion']})")])
terminal('t06-hurl', [('docker run --rm --network traveler_lab6_backend ghcr.io/orange-opensource/hurl:8.0.0 --test --variable host=http://web:4567 /tests/*.hurl', read('sharded-hurl.txt'))])
terminal('t07-concurrency', [('node --test tests/concurrency.test.js', read('sharded-concurrency.txt'))])
terminal('t08-dry-run', [(f'{TOOLS} tools/shard-exec.js /sql/010_schema_migrations.sql --dry-run', body('tools-01-dry-run.txt'))])
terminal('t09-commit', [(f'{TOOLS} tools/shard-exec.js /sql/010_schema_migrations.sql --show-prepared', body('tools-02-commit.txt'))])
terminal('t10-failure', [('curl -X POST http://127.0.0.1:4567/api/travel-plans -d \'{"title":"Expensive trip ...","budget":9000}\'', j('tools-04-expensive-plan.json')),
                         (f'{TOOLS} tools/shard-exec.js /sql/020_budget_limit_fails.sql', body('tools-05-failure.txt'))], width=1500)
terminal('t11-state-after-failure', [('python scripts/lab6/demo_tools.py   # state of all 16 databases after the failed run', read('tools-06-state-after-failure.txt'))])
terminal('t12-refused', [(f'{TOOLS} tools/shard-exec.js /sql/030_own_transaction.sql', body('tools-07-refused.txt')),
                         (f'{TOOLS} tools/shard-exec.js /sql/040_check_shard_keys.sql', body('tools-08-invariant.txt'))])
terminal('t13-security', [('psql -d db_5   # roles, table privileges of the API role, pg_hba rules', read('topology-security.txt'))], width=1300)
terminal('t14-registry', [('psql shard_registry   # publication, slots and subscriptions', read('topology-registry.txt'))])
for tag in ('rebalance-file', 'rebalance-registry'):
    drop = ' --drop-source' if tag.endswith('registry') else ''
    terminal(f't15-{tag}-status-before', [(f'{TOOLS} tools/rebalance.js status', read(f'{tag}-status-before.txt'))])
    terminal(f't16-{tag}-move-db3', [(f'{TOOLS} tools/rebalance.js move db_3 postgres_03{drop}', body(f'{tag}-move-db_3.txt'))])
    terminal(f't17-{tag}-move-db7', [(f'{TOOLS} tools/rebalance.js move db_7 postgres_02{drop}', body(f'{tag}-move-db_7.txt'))])
    terminal(f't18-{tag}-status-after', [(f'{TOOLS} tools/rebalance.js status', read(f'{tag}-status-after.txt'))])
    terminal(f't19-{tag}-api-logs', [(f'{DC} logs web web2 | findstr "mapping_loaded shard_retry"', read(f'{tag}-api-logs.txt'))], width=1500)
    terminal(f't20-{tag}-k6', [(f'k6 run tests/performance-tests/rebalance-test.js   # 60 VU, 100 s, two API instances', read(f'{tag}/rebalance-summary.txt'))], width=1500)
for tag in ('baseline-load', 'baseline-2api-load', 'sharded-naive-load', 'sharded-equal-load', 'sharded-scaled-load', 'sharded-scaled-2api-load'):
    terminal(f't21-{tag}', [('k6 run tests/performance-tests/load-test.js', read(f'{tag}/load-summary.txt'))], width=1500)
terminal('t22-list-order', [('python scripts/lab6/verify_list.py', read('list-order-check.txt'))])
terminal('t23-hurl-after', [('hurl --test /tests/*.hurl   # after both moves (mapping file)', read('rebalance-file-after-hurl.txt')),
                            ('hurl --test /tests/*.hurl   # after both moves (registry)', read('rebalance-registry-after-hurl.txt'))])
terminal('t24-registry-map', [('psql -h postgres_02 -d shard_registry -c "SELECT * FROM shard_map"   # copy on postgres_02', read('rebalance-registry-registry.txt'))])
print('ALL SHOTS DONE')
