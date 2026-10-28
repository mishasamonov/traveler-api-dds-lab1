"""Package the verified report and runnable project, including raw measurements."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib,json
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT.parent/'output'
report=OUT/'TravelerAPI_Lab3_Samonov.docx'
assert report.exists()
excluded={'.git','node_modules','.pgdata','__pycache__','.captures','output'}
paths=[p for p in ROOT.rglob('*') if p.is_file() and not any(x in excluded for x in p.relative_to(ROOT).parts) and p.name!='.env' and not p.name.endswith(('.pyc','.log'))]
target=OUT/'TravelerAPI_Lab3_Samonov.zip'
with ZipFile(target,'w',ZIP_DEFLATED,compresslevel=6) as z:
 z.write(report,report.name)
 for p in paths:z.write(p,'traveler-api-lab3/'+p.relative_to(ROOT).as_posix())
 with z.open('DELIVERY.txt','w') as f:f.write('Лабораторна робота 3 Самонов Михайло\nЗвіт: TravelerAPI_Lab3_Samonov.docx\nКод і докази: traveler-api-lab3/\nЗапуск: створити .env за .env.example та docker compose up --build\nПовторення вимірювань: docs/lab3-docker.md\nУ results-docker збережені також сирі gzip JSON і HTML dashboards.\n'.encode('utf-8'))
with ZipFile(target) as z:
 assert not any(Path(n).name=='.env' or '/.git/' in n or '/node_modules/' in n for n in z.namelist())
 assert z.testzip() is None
print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'files':len(paths)+2,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False))
