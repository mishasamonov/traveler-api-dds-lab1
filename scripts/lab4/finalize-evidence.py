import json,re
from pathlib import Path
import lab
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('security',Path(__file__).with_name('verify-security.py'));security=module_from_spec(spec);spec.loader.exec_module(security)
security.verify('pgcat')
mode='pgcat'
raw=(lab.OUT/'pgcat-security.txt').read_text(encoding='utf-8')
lab.save('pgcat-security-full.txt',raw)
compact=raw.split('\nNAME ')[0]
compact='\n'.join(s for s in compact.splitlines() if s.strip() and not re.fullmatch(r'\(\d+ rows?\)',s.strip()))
lab.save('pgcat-security.txt',compact+'\n')
full=lab.dc(mode,'ps',capture_output=True).stdout;lab.save('pgcat-compose-ps-full.txt',full)
ports=['docker inspect: HostConfig.PortBindings','Only published HOST ports are listed below','']
for ident in lab.dc(mode,'ps','-q',capture_output=True).stdout.split():
    name=lab.cmd(['docker','inspect','--format','{{index .Config.Labels "com.docker.compose.service"}}',ident],mode,capture_output=True).stdout.strip()
    bindings=json.loads(lab.cmd(['docker','inspect','--format','{{json .HostConfig.PortBindings}}',ident],mode,capture_output=True).stdout)
    rendered=[]
    for inside,items in (bindings or {}).items():
        for item in items or []:rendered.append(f"{item['HostIp']}:{item['HostPort']} -> {inside}")
    ports.append(f'{name:10} '+(', '.join(rendered) if rendered else 'NONE'))
lab.save('pgcat-compose-ps.txt','\n'.join(ports)+'\n')
web=lab.dc(mode,'ps','-q','web',capture_output=True).stdout.strip()
tests=lab.cmd(['docker','run','--rm','--network','container:'+web,'-v',str(lab.ROOT/'tests')+':/app/tests:ro','traveler-api:lab4','node','--test','tests/concurrency.test.js'],mode,capture_output=True,check=False)
lab.save('pgcat-concurrency.txt',tests.stdout+'\n'+tests.stderr)
assert tests.returncode==0,tests.stdout+tests.stderr
lab.save('pgcat-final-data-equality.json',lab.wait_equal(mode))
lab.save('environment.txt',lab.cmd(['docker','version','--format','Client {{.Client.Version}}; Server {{.Server.Version}}'],mode,capture_output=True).stdout+
    lab.dc(mode,'exec','-T','web','node','--version',capture_output=True).stdout+
    lab.sql(mode,'postgres','SELECT version(); SHOW wal_keep_size; SHOW max_connections; SHOW shared_buffers;')+'\n'+
    lab.dc(mode,'exec','-T','pgcat','pgcat','--version',capture_output=True).stdout)
print('Security, ports, three concurrency tests and final data equality verified')
