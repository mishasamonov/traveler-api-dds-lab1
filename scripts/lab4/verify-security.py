import json
import lab
def verify(mode):
    ids=lab.dc(mode,'ps','-q',capture_output=True).stdout.split()
    views=[]
    for ident in ids:
        raw=lab.cmd(['docker','inspect','--format','{{json .HostConfig.PortBindings}}',ident],mode,capture_output=True).stdout
        name=lab.cmd(['docker','inspect','--format','{{.Name}}',ident],mode,capture_output=True).stdout.strip()
        views.append({'container':name,'publishedPorts':json.loads(raw)})
    assert sum(bool(x['publishedPorts']) for x in views)==1
    for item in views:
        if item['publishedPorts']:
            assert item['publishedPorts']['4567/tcp'][0]['HostIp']=='127.0.0.1'
    role=lab.sql(mode,'postgres',"SELECT rolname,rolsuper,rolreplication,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname IN ('traveler','lab4_repl'); SELECT has_table_privilege('traveler','travel_plans','TRUNCATE') AS app_can_truncate;")
    rejected=lab.dc(mode,'exec','-T','postgres','sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"',capture_output=True,check=False)
    assert rejected.returncode!=0 and 'rejects connection' in rejected.stderr
    output='Published host ports (from docker inspect)\n'+json.dumps(views,indent=2)+'\n\n'+role+'\n\nAdmin TCP login rejected by pg_hba.conf\n'+rejected.stderr
    lab.save(mode+'-security-verification.txt',output)
    print('Verified security',mode)
if __name__=='__main__':
    import sys;verify(sys.argv[1] if len(sys.argv)>1 else 'pgcat')
