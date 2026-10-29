"""Verify actual run outcomes and report evidence before delivery."""
from pathlib import Path
import gzip,hashlib,json,zipfile
R=Path(__file__).resolve().parents[2];E=R/'evidence/lab4'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    runs=[]
    for file in sorted(E.glob('*-run.json')):
        value=read(file);prefix=file.name.removesuffix('-run.json');scenario=value['scenario']
        summary=read(E/prefix/(scenario+'-summary.json'))['metrics']
        assert value['exitCode'] in (0,99),(file,value['exitCode'])
        assert summary['http_req_failed']['values']['rate']==0,file
        assert summary['checks']['values']['rate']==1,file
        if scenario=='smoke':assert value['exitCode']==0,file
        checks=read(E/(prefix+'-data-equality.json'));first=checks['postgres']
        assert first['plans']==2000 and first['locations']==6000,(file,first)
        assert all(x==first for x in checks.values()),file
        assert (E/(prefix+'-raw.json.gz')).stat().st_size>0
        runs.append({'run':prefix,'exitCode':value['exitCode'],'requests':summary['http_reqs']['values']['count'],'HTTPerrors':0,'checksRate':1,'copiesEqual':True})
    assert len(runs)==16,len(runs)
    for mode in ['baseline','logical','physical','sync','logical2','two','pgcat']:
        assert read(E/(mode+'-hurl-exit.json'))['exitCode']==0
    block=(E/'sync-sync-block.txt').read_text();assert 'SyncRep' in block and 'True' in block and 'UPDATE 1' in block
    assert read(E/'logical-ddl.json')['immediatelyAfterPrimaryDDL']['postgres_sub']=='ABSENT'
    assert read(E/'physical-ddl.json')['immediatelyAfterPrimaryDDL']['replica1']=='lab4_ddl_probe'
    routing=read(E/'pgcat-routing.txt');assert len(routing['reads'])==2
    assert sum(routing['reads'].values())==200 and routing['writes'][0]['standby'] is False
    continuity=read(E/'source-continuity.json');assert all(x['unchanged'] for x in continuity.values())
    result={'verifiedRuns':runs,'hurlTopologies':7,'sourceFilesUnchanged':len(continuity),'synchronousWaitProved':True,'logicalAndPhysicalDDLProved':True,'PgCatReadWriteRoutingProved':True}
    (E/'delivery-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Verified',len(runs),'k6 runs and 7 Hurl topologies')
if __name__=='__main__':main()
