"""Package source, genuine evidence, raw measurements, and local Git history."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
R=Path(__file__).resolve().parents[2];OUT=R.parent/'output/lab4';OUT.mkdir(parents=True,exist_ok=True)
bundle=OUT/'TravelerAPI_Lab4_History.bundle'
subprocess.run(['git','bundle','create',str(bundle),'lab4-replication'],cwd=R,check=True)
subprocess.run(['git','bundle','verify',str(bundle)],cwd=R,check=True,capture_output=True)
files=[]
for name in ['README.md','README-LAB4.md','Dockerfile','docker-compose.yml','.env.example','.dockerignore','.gitignore','.gitattributes','package.json','package-lock.json']:
    files.append(R/name)
for folder in ['src','db/migrations','db/replications','pgcat','scripts/lab4','evidence/lab4']:
    files.extend(p for p in (R/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for name in ['db/schema.sql','db/002_location_version.sql','scripts/init-db.js','scripts/seed-container.cjs','scripts/build-lab2-report.py','tests/crud.hurl','tests/validation.hurl','tests/management.hurl','tests/race-conditions.hurl','tests/concurrency.test.js','tests/variables.properties']:
    files.append(R/name)
perf=R/'tests/performance-tests'
files.extend(perf.glob('*-test.js'))
for folder in ['utils','config']:
    files.extend(p for p in (perf/folder).rglob('*') if p.is_file())
secrets=[]
for line in (R/'.env').read_text().splitlines():
    if '=' in line and 'PASSWORD=' in line:secrets.append(line.split('=',1)[1].encode())
for p in files:
    data=p.read_bytes()
    assert not any(secret in data for secret in secrets),f'Credential detected in {p.name}'
target=OUT/'TravelerAPI_Lab4_Samonov.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(set(files)):z.write(p,'TravelerAPI_Lab4/'+p.relative_to(R).as_posix())
    z.write(bundle,'TravelerAPI_Lab4/lab4-history.bundle')
    report=OUT/'TravelerAPI_Lab4_Samonov.docx'
    assert report.exists()
    z.write(report,'TravelerAPI_Lab4/TravelerAPI_Lab4_Samonov.docx')
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert not any(n.endswith('/.env') or '/.runtime/' in n or '/node_modules/' in n or '/.git/' in n for n in z.namelist())
verification={'archive':target.name,'files':len(files)+2,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'credentialsExcluded':True,'gitBundleVerified':True}
(OUT/'package-verification.json').write_text(json.dumps(verification,indent=2));print(json.dumps(verification,indent=2))
