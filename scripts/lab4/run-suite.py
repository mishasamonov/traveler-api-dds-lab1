import argparse,json,subprocess,time
from pathlib import Path
import lab
def sync_block(mode):
    args=['docker','compose','exec','-T','postgres','psql','-X','-v','ON_ERROR_STOP=1','-U',lab.load_env()['DB_ADMIN'],'-d',lab.load_env()['DB_NAME']]
    lab.dc(mode,'pause','replica1',capture_output=True)
    begin=time.monotonic();process=None
    try:
        process=subprocess.Popen(args,cwd=lab.ROOT,env=lab.environment(mode),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        process.stdin.write("UPDATE travel_plans SET version=version+1 WHERE id=(SELECT id FROM travel_plans ORDER BY id LIMIT 1);\n");process.stdin.close();process.stdin=None
        observed=''
        for _ in range(30):
            observed=lab.sql(mode,'postgres',"SELECT application_name,wait_event_type,wait_event FROM pg_stat_activity WHERE wait_event='SyncRep';")
            if 'SyncRep' in observed:break
            time.sleep(.5)
        if 'SyncRep' not in observed:raise RuntimeError('No synchronous commit wait observed')
        time.sleep(2)
        pending=process.poll() is None
    finally:lab.dc(mode,'unpause','replica1',capture_output=True)
    out,err=process.communicate(timeout=60)
    assert pending and process.returncode==0
    lab.save(mode+'-sync-block.txt','Paused replica1. Primary backend observed:\n'+observed+'\n\nCommit still pending before unpause: '+str(pending)+'\nAfter unpause: '+out+f'Elapsed seconds: {time.monotonic()-begin:.3f}\n')
def routing(mode):
    source="""const {pool}=require('./src/db');(async()=>{
      const reads={}; for(let i=0;i<200;i++){const r=await pool.query('SELECT inet_server_addr()::text AS host,pg_is_in_recovery() AS standby');const k=JSON.stringify(r.rows[0]);reads[k]=(reads[k]||0)+1;}
      const writes=await pool.query('UPDATE travel_plans SET version=version+1 WHERE id=(SELECT id FROM travel_plans ORDER BY id LIMIT 1) RETURNING inet_server_addr()::text AS host,pg_is_in_recovery() AS standby');
      console.log(JSON.stringify({reads,writes:writes.rows},null,2));})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>pool.end());"""
    result=lab.dc(mode,'exec','-T','web','node','-e',source,capture_output=True)
    parsed=json.loads(result.stdout);assert len(parsed['reads'])==2
    assert all(json.loads(k)['standby'] for k in parsed['reads']) and parsed['writes'][0]['standby'] is False
    lab.save(mode+'-routing.txt',result.stdout)
def run(modes,k6):
    for mode in modes:
        print('START MODE',mode,flush=True);lab.up(mode)
        if lab.functional(mode)!=0:raise RuntimeError('Hurl failed for '+mode)
        lab.seed(mode);lab.proof(mode)
        if mode in ('logical','physical'):lab.ddl(mode)
        if mode=='sync':sync_block(mode)
        if mode=='pgcat':routing(mode)
        if mode not in ('logical2','two'):
            lab.benchmark(mode,'smoke',k6)
            lab.benchmark(mode,'load',k6)
        if mode in ('two','pgcat'):
            for i in range(1,4):lab.benchmark(mode,'read',k6,tag=f'{mode}-read-{i}')
        print('COMPLETE MODE',mode,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--k6',type=Path,required=True);p.add_argument('--modes',nargs='+',default=['logical','physical','sync','logical2','two','pgcat']);a=p.parse_args();run(a.modes,a.k6.resolve())
