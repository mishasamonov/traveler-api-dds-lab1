"""Run the unchanged lab 2 k6 scenarios sequentially and retain Docker telemetry."""
import argparse, datetime, json, os, pathlib, subprocess, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / 'tests/performance-tests/results-docker'
DOCKER = ['docker', 'compose']

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def command(args, **kw):
    return subprocess.run(args, cwd=ROOT, text=True, encoding='utf-8', check=True, **kw)

def run(name, k6):
    RESULTS.mkdir(parents=True, exist_ok=True)
    seed = command(DOCKER + ['exec','-T','web','node','scripts/seed-container.cjs'], capture_output=True)
    plans = json.loads(seed.stdout)
    assert len(plans) == 2000
    (ROOT/'tests/performance-tests/seed.json').write_text(json.dumps(plans), encoding='utf-8')
    env = os.environ.copy()
    relative = RESULTS.relative_to(ROOT).as_posix()
    env.update(K6_WEB_DASHBOARD='true', K6_WEB_DASHBOARD_PORT='-1',
               K6_WEB_DASHBOARD_PERIOD='5s', K6_WEB_DASHBOARD_EXPORT=f'{relative}/{name}-dashboard.html',
               RESULT_DIR=relative, API_URL='http://127.0.0.1:4567')
    args = [str(k6),'run','--out',f'json={relative}/{name}-raw.json.gz',f'tests/performance-tests/{name}-test.js']
    metadata = dict(test=name, startedUtc=now(), command=args, apiUrl=env['API_URL'],
        database='traveler_lab2 in isolated Docker volume', seedPlans=2000, seedLocations=6000,
        node='v22.18.0', pgPoolMax=20, webLimits={'cpus':2,'memoryMiB':512},
        dbLimits={'cpus':2,'memoryMiB':1024}, databaseMode='Docker Desktop Linux containers on Windows')
    (RESULTS/f'{name}-run.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    start=time.monotonic()
    print(f'{now()} START {name}', flush=True)
    with (RESULTS/f'{name}-console.txt').open('w',encoding='utf-8') as out, \
         (RESULTS/f'{name}-stderr.txt').open('w',encoding='utf-8') as err, \
         (RESULTS/f'{name}-docker-stats.jsonl').open('w',encoding='utf-8') as telemetry:
        process=subprocess.Popen(args,cwd=ROOT,env=env,stdout=out,stderr=err)
        ids=command(DOCKER+['ps','-q'],capture_output=True).stdout.split()
        while process.poll() is None:
            stamp=now()
            sampled=subprocess.run(['docker','stats','--no-stream','--format','{{json .}}',*ids],
                cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            for line in sampled.stdout.splitlines():
                telemetry.write(json.dumps({'timestamp':stamp,**json.loads(line)})+'\n')
            telemetry.flush()
            time.sleep(5)
        code=process.wait()
    metadata.update(finishedUtc=now(),exitCode=code,elapsedSeconds=time.monotonic()-start)
    (RESULTS/f'{name}-run.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    check=subprocess.run(DOCKER+['exec','-T','web','node','scripts/check-container-data.cjs'],
        cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    (RESULTS/f'{name}-data-check.json').write_text(check.stdout,encoding='utf-8')
    metadata['dataCheckExitCode']=check.returncode
    (RESULTS/f'{name}-run.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(f'{now()} FINISH {name} exit={code} elapsed={metadata["elapsedSeconds"]:.1f}s',flush=True)
    print((RESULTS/f'{name}-summary.txt').read_text(encoding='utf-8'),flush=True)
    if code not in (0,99): raise RuntimeError(f'Unexpected k6 exit {code}')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--k6',type=pathlib.Path,required=True)
    parser.add_argument('--tests',nargs='+',default=['smoke','load','stress','spike','endurance'])
    a=parser.parse_args()
    for name in a.tests:
        if name not in ['smoke','load','stress','spike','endurance']: raise ValueError(name)
        run(name,a.k6.resolve())
