"""Evidence of the deployed topology: services, databases, roles, registry replication."""
import json, sys, urllib.request
sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from lab6 import save, psql, load_env, dc, NODES

env = load_env()
parts = []
for node in NODES:
    dbs = psql('sharded', node, 'postgres', """SELECT string_agg(datname || ' (' || pg_size_pretty(pg_database_size(datname)) || ')', ', ' ORDER BY datname)
      FROM pg_database WHERE datname ~ '^(db_|shard_registry)'""")
    settings = psql('sharded', node, 'postgres', "SELECT string_agg(name || '=' || setting, ', ' ORDER BY name) FROM pg_settings WHERE name IN ('wal_level','max_prepared_transactions','max_connections','max_replication_slots')")
    parts.append(f'{node}: {dbs}\n  {settings}')
save('topology-databases.txt', '\n'.join(parts))

reg = ['postgres_00 (publisher):\n' + psql('sharded', 'postgres_00', 'shard_registry', 'SELECT pubname, string_agg(tablename, \', \') FROM pg_publication_tables GROUP BY pubname;', tuples=False)
       + psql('sharded', 'postgres_00', 'postgres', 'SELECT slot_name, plugin, database, active FROM pg_replication_slots ORDER BY slot_name;', tuples=False)]
for node in NODES[1:]:
    reg.append(f'{node} (subscriber):\n' + psql('sharded', node, 'shard_registry', """SELECT s.subname, s.subenabled, st.received_lsn, st.latest_end_lsn
      FROM pg_subscription s JOIN pg_stat_subscription st ON st.subid = s.oid WHERE st.relid IS NULL;
      SELECT m.version, count(*) AS shards FROM registry_meta m, shard_map GROUP BY m.version;""", tuples=False))
save('topology-registry.txt', '\n'.join(reg))
save('topology-registry-map.txt', psql('sharded', 'postgres_02', 'shard_registry', 'SELECT shard, host, port, database FROM shard_map ORDER BY shard;', tuples=False))
save('topology-security.txt', psql('sharded', 'postgres_01', 'db_5', f"""SELECT rolname, rolsuper, rolreplication, rolcreatedb FROM pg_roles WHERE rolname IN ('{env['APP_USER']}','{env['REPL_USER']}','{env['DB_ADMIN']}') ORDER BY rolname;
  SELECT grantee, string_agg(privilege_type, ',' ORDER BY privilege_type) FROM information_schema.role_table_grants WHERE table_name = 'travel_plans' AND grantee = '{env['APP_USER']}' GROUP BY grantee;
  SELECT type, database, user_name, address, auth_method FROM pg_hba_file_rules;""", tuples=False))
for port in (4567, 4568):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health') as r: save(f'topology-health-{port}.json', json.loads(r.read()))
with urllib.request.urlopen('http://127.0.0.1:4567/api/shards') as r: save('topology-api-shards.json', json.loads(r.read()))
save('topology-compose-ps.txt', dc('sharded', 'ps', '--format', 'table {{.Service}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}', capture_output=True).stdout)
print('TOPOLOGY saved')
