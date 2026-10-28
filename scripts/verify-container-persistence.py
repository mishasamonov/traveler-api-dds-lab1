"""After all measurements, prove a synthetic record survives container recreation."""
import json,subprocess,urllib.request,pathlib,datetime
ROOT=pathlib.Path(__file__).resolve().parent.parent
meta=json.loads((ROOT/'tests/performance-tests/results-docker/endurance-run.json').read_text())
if 'finishedUtc' not in meta:raise RuntimeError('Do not restart services during the endurance measurement')
URL='http://127.0.0.1:4567'
def req(method,path,body=None):
 data=None if body is None else json.dumps(body).encode()
 request=urllib.request.Request(URL+path,data=data,method=method,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(request) as r:return r.status,(json.loads(r.read()) if r.status!=204 else None)
def cmd(*args):return subprocess.check_output(args,cwd=ROOT,text=True,encoding='utf-8').strip()
status,plan=req('POST','/api/travel-plans',{'title':'Lab3 named volume persistence check'})
assert status==201
old=cmd('docker','compose','ps','-q','postgres')
subprocess.run(['docker','compose','down'],cwd=ROOT,check=True)
subprocess.run(['docker','compose','up','-d','--wait'],cwd=ROOT,check=True)
new=cmd('docker','compose','ps','-q','postgres')
status,found=req('GET',f'/api/travel-plans/{plan["id"]}')
assert status==200 and found['id']==plan['id'] and found['title']==plan['title'] and old!=new
deleted,_=req('DELETE',f'/api/travel-plans/{plan["id"]}');assert deleted==204
proof={'checkedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'planId':plan['id'],
 'beforeContainer':old,'afterContainer':new,'readAfterRecreationStatus':status,'cleanupStatus':deleted,'namedVolume':'traveler_lab3_postgres_data'}
(ROOT/'evidence/persistence.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
text=f'''POST /api/travel-plans -> 201
Control plan: {plan['id']}
docker compose down (without -v)
docker compose up -d --wait
GET /api/travel-plans/{plan['id']} -> {status}
Same id and title: PASS
Database container was recreated: PASS
Named volume: traveler_lab3_postgres_data
DELETE control plan -> {deleted}
'''
(ROOT/'evidence/persistence.txt').write_text(text,encoding='utf-8')
print(text)
