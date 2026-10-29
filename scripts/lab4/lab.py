"""Reproducible isolated replication experiments. No existing lab data is removed."""
import argparse, datetime, hashlib, json, os, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/lab4';OUT.mkdir(parents=True,exist_ok=True)
MODES={'baseline':[], 'logical':['logical'], 'physical':['physical'], 'sync':['physical'],
       'two':['physical','physical2'], 'pgcat':['physical','physical2','pooler'], 'logical2':['logical','logical2']}
def load_env():
    values={}
    for line in (ROOT/'.env').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1);values[key]=value
    return values
def environment(mode):
    env=os.environ.copy();env.update(load_env())
    env.update(COMPOSE_PROJECT_NAME='traveler_lab4_'+mode,COMPOSE_PROFILES=','.join(MODES[mode]),
      DOCKER_SUBNET=f'172.29.{41+list(MODES).index(mode)}.0/24',
      PG_HOST='pgcat' if mode=='pgcat' else 'postgres',PG_PORT='6432' if mode=='pgcat' else '5432')
    return env
def cmd(args,mode,check=True,**kw):
    return subprocess.run(args,cwd=ROOT,env=environment(mode),text=True,encoding='utf-8',check=check,**kw)
def dc(mode,*args,**kw):return cmd(['docker','compose',*args],mode,**kw)
def sql(mode,service,query,tuples=False):
    args=['exec','-T',service,'psql','-X','-v','ON_ERROR_STOP=1','-U',load_env()['DB_ADMIN'],'-d',load_env()['DB_NAME']]
    if tuples:args+=['-At']
    return dc(mode,*args,input=query,capture_output=True).stdout.strip()
def save(name,value):
    path=OUT/name
    path.write_text(value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
def replicas(mode):
    return {'baseline':[], 'logical':['postgres_sub'], 'logical2':['postgres_sub','postgres_sub2'],
      'physical':['replica1'],'sync':['replica1'],'two':['replica1','replica2'],'pgcat':['replica1','replica2']}[mode]
def up(mode):
    active=ROOT/'.runtime/active.json'
    if active.exists():
        old=json.loads(active.read_text())['mode']
        if old!=mode:dc(old,'stop',capture_output=True)
    (ROOT/'.runtime').mkdir(exist_ok=True)
    values=load_env()
    text=(ROOT/'pgcat/pgcat.toml.template').read_text()
    for key in ('APP_USER','APP_PASSWORD','PGCAT_ADMIN_PASSWORD'):text=text.replace('${'+key+'}',values[key])
    (ROOT/'.runtime/pgcat.toml').write_text(text,encoding='utf-8')
    dc(mode,'up','-d','--wait','postgres',*replicas(mode))
    # Configure only after standby bootstrap; otherwise synchronous initdb would deadlock.
    names='ANY 2 (replica1, replica2)' if mode in ('two','pgcat') else 'FIRST 1 (replica1)' if mode=='sync' else ''
    sql(mode,'postgres',f"ALTER SYSTEM SET synchronous_standby_names = '{names}';")
    sql(mode,'postgres',"ALTER SYSTEM SET synchronous_commit = 'remote_apply';" if names else "ALTER SYSTEM SET synchronous_commit = 'on';")
    sql(mode,'postgres','SELECT pg_reload_conf();')
    if names:
        for _ in range(90):
            states=sql(mode,'postgres',"SELECT count(*) FROM pg_stat_replication WHERE state='streaming' AND sync_state IN ('sync','quorum');",True)
            if int(states)==len(replicas(mode)):break
            time.sleep(1)
        else:raise RuntimeError('Synchronous replicas did not become ready')
    if mode=='pgcat':dc(mode,'up','-d','pgcat')
    dc(mode,'up','-d','--wait','--build','web')
    active.write_text(json.dumps({'mode':mode}),encoding='utf-8')
    save(f'{mode}-compose-ps.txt',dc(mode,'ps',capture_output=True).stdout)
    print('READY',mode,flush=True)
def seed(mode):
    source=(ROOT/'scripts/seed-container.cjs').read_text()
    # Keep the exact lab 2 data generation. This opt-in is confined to this disposable project.
    # Seed via the local admin on the primary; the API role has no TRUNCATE privilege.
    body=source[source.index("  await pool.query('TRUNCATE"):source.index('  const { rows } = await pool.query')]
    # Admin is intentionally not admitted over TCP; use psql and the original SQL statements.
    import re
    statements=re.findall(r"await pool.query\((?:`([^`]+)`|'([^']+)')\);",body)
    for block in statements:sql(mode,'postgres',next(s for s in block if s))
    rows=json.loads(sql(mode,'postgres',"SELECT json_agg(t) FROM (SELECT id FROM travel_plans ORDER BY id) t;",True))
    assert len(rows)==2000
    (ROOT/'tests/performance-tests/seed.json').write_text(json.dumps(rows),encoding='utf-8')
    wait_equal(mode)
def fingerprint(mode,service):
    query="""SELECT json_build_object('plans',(SELECT count(*) FROM travel_plans),
      'locations',(SELECT count(*) FROM locations),
      'plans_md5',(SELECT md5(string_agg(row_to_json(t)::text,E'\\n' ORDER BY id)) FROM travel_plans t),
      'locations_md5',(SELECT md5(string_agg(row_to_json(t)::text,E'\\n' ORDER BY id)) FROM locations t));"""
    return json.loads(sql(mode,service,query,True))
def wait_equal(mode):
    master=fingerprint(mode,'postgres')
    for _ in range(120):
        copies={r:fingerprint(mode,r) for r in replicas(mode)}
        if all(v==master for v in copies.values()):return {'postgres':master,**copies}
        time.sleep(.5)
    raise RuntimeError('Replica data failed to converge')
def proof(mode):
    result=wait_equal(mode);save(f'{mode}-data-equality.json',result)
    replication=sql(mode,'postgres',"SELECT application_name,state,sync_state,write_lsn,flush_lsn,replay_lsn FROM pg_stat_replication ORDER BY application_name;")
    settings=sql(mode,'postgres',"SHOW wal_level; SHOW synchronous_commit; SHOW synchronous_standby_names;")
    save(f'{mode}-replication.txt',settings+'\n\n'+replication+'\n\n'+json.dumps(result,indent=2))
    if mode in ('logical','logical2'):
        save(f'{mode}-subscriptions.txt','\n\n'.join(r+'\n'+sql(mode,r,"SELECT subname,subenabled FROM pg_subscription; SELECT srrelid::regclass,srsubstate FROM pg_subscription_rel;") for r in replicas(mode)))
    if replicas(mode):
        # Real INSERT / UPDATE / DELETE and full-row equality after every stage.
        stages=[]
        probe='00000000-0000-4000-8000-000000000004'
        for label,q in [
          ('INSERT',f"INSERT INTO travel_plans(id,title) VALUES ('{probe}','Lab4 replication probe') ON CONFLICT(id) DO UPDATE SET title=excluded.title;"),
          ('UPDATE',f"UPDATE travel_plans SET title='Lab4 updated probe',version=version+1 WHERE id='{probe}';"),
          ('DELETE',f"DELETE FROM travel_plans WHERE id='{probe}';")]:
            sql(mode,'postgres',q);stages.append({'operation':label,'equal':wait_equal(mode)})
        save(f'{mode}-crud-replication.json',stages)
    save(f'{mode}-security.txt',sql(mode,'postgres',"SELECT rolname,rolsuper,rolreplication,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname IN ('traveler','lab4_repl'); SHOW password_encryption; SHOW listen_addresses; SELECT type,database,user_name,address,auth_method,error FROM pg_hba_file_rules;")+'\n\n'+dc(mode,'ps',capture_output=True).stdout)
    print('PROOF',mode,'all copies equal',flush=True)
def functional(mode):
    output=cmd(['docker','run','--rm','--network',environment(mode)['COMPOSE_PROJECT_NAME']+'_backend',
      '-v',str(ROOT/'tests')+':/tests:ro','ghcr.io/orange-opensource/hurl:8.0.0','--test',
      '--variable','host=http://web:4567','/tests/crud.hurl','/tests/validation.hurl','/tests/management.hurl','/tests/race-conditions.hurl'],mode,capture_output=True,check=False)
    save(f'{mode}-hurl.txt',output.stdout+'\n'+output.stderr)
    save(f'{mode}-hurl-exit.json',{'exitCode':output.returncode})
    print('HURL',mode,output.returncode,flush=True)
    return output.returncode
def benchmark(mode,name,k6,tag=None):
    seed(mode)
    prefix=tag or f'{mode}-{name}'
    result_dir=f'evidence/lab4/{prefix}'
    (ROOT/result_dir).mkdir(exist_ok=True)
    env=environment(mode);env.update(API_URL='http://127.0.0.1:4567',RESULT_DIR=result_dir)
    script=ROOT/('tests/performance-tests/'+name+'-test.js')
    args=[str(k6),'run','--out',f'json=evidence/lab4/{prefix}-raw.json.gz',str(script)]
    meta={'mode':mode,'scenario':name,'startedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'command':[str(Path(k6).name),*args[1:]],'seedPlans':2000,'seedLocations':6000,
      'apiSourceSHA256':hashlib.sha256((ROOT/'src/app.js').read_bytes()).hexdigest(),
      'scenarioSHA256':hashlib.sha256(script.read_bytes()).hexdigest(),'replicas':replicas(mode)}
    start=time.monotonic()
    with (OUT/f'{prefix}-console.txt').open('w',encoding='utf-8') as out, (OUT/f'{prefix}-docker-stats.jsonl').open('w',encoding='utf-8') as stats:
        proc=subprocess.Popen(args,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            for line in dc(mode,'ps','-q',capture_output=True).stdout.splitlines():
                result=cmd(['docker','stats','--no-stream','--format','{{json .}}',line],mode,capture_output=True,check=False)
                for row in result.stdout.splitlines():stats.write(json.dumps({'at':time.time(),**json.loads(row)})+'\n')
            stats.flush();time.sleep(3)
        meta.update(exitCode=proc.wait(),elapsedSeconds=time.monotonic()-start)
    save(prefix+'-run.json',meta)
    if name=='read': summary=ROOT/result_dir/'read-summary.json'
    else:summary=ROOT/result_dir/(name+'-summary.json')
    values=json.loads(summary.read_text())['metrics']
    save(prefix+'-data-equality.json',wait_equal(mode))
    print('BENCHMARK',prefix,'exit',meta['exitCode'],'p95',values['http_req_duration']['values']['p(95)'],'req/s',values['http_reqs']['values']['rate'],flush=True)
    if meta['exitCode'] not in (0,99):raise RuntimeError('Unexpected k6 failure')
def ddl(mode):
    sql(mode,'postgres','CREATE TABLE IF NOT EXISTS lab4_ddl_probe(id integer PRIMARY KEY, note text);')
    observed={r:sql(mode,r,"SELECT coalesce(to_regclass('public.lab4_ddl_probe')::text,'ABSENT');",True) for r in replicas(mode)}
    if mode in ('logical','logical2'):
        for r in replicas(mode):
            sql(mode,r,'CREATE TABLE IF NOT EXISTS lab4_ddl_probe(id integer PRIMARY KEY, note text);')
            sql(mode,r,'ALTER SUBSCRIPTION '+('tp_sub2' if r.endswith('2') else 'tp_sub1')+' REFRESH PUBLICATION;')
    sql(mode,'postgres',"INSERT INTO lab4_ddl_probe VALUES(4,'DDL and row verification') ON CONFLICT(id) DO UPDATE SET note=excluded.note;")
    for _ in range(60):
        if any(sql(mode,r,"SELECT to_regclass('public.lab4_ddl_probe') IS NOT NULL;",True)!='t' for r in replicas(mode)):
            time.sleep(.5);continue
        rows={r:sql(mode,r,'TABLE lab4_ddl_probe;',True) for r in replicas(mode)}
        if all('DDL and row verification' in x for x in rows.values()):break
        time.sleep(.5)
    else:raise RuntimeError('DDL replication demonstration failed')
    save(f'{mode}-ddl.json',{'immediatelyAfterPrimaryDDL':observed,'afterDDLAndRowReplication':rows})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['up','seed','proof','functional','benchmark','ddl','stop']);p.add_argument('mode',choices=MODES)
    p.add_argument('--test',default='load');p.add_argument('--tag');p.add_argument('--k6',type=Path)
    a=p.parse_args()
    if a.action=='benchmark':benchmark(a.mode,a.test,a.k6.resolve(),a.tag)
    elif a.action=='stop':dc(a.mode,'stop')
    else:globals()[a.action](a.mode)
