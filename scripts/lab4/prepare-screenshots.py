"""Lossless crops of genuine browser captures. No reconstruction or resampling."""
from pathlib import Path
from PIL import Image,ImageChops,ImageFilter
import hashlib,json
R=Path(__file__).resolve().parents[2]/'evidence/lab4/screenshots'
dest=R/'crops';dest.mkdir(exist_ok=True)
manifest=[]
sources={'01-baseline-hurl':'baseline-hurl.txt','02-logical-equality':'logical-data-equality.json',
'03-logical-subscriptions':'logical-subscriptions.txt','04-logical-smoke':'logical-smoke/smoke-summary.txt',
'05-logical-ddl':'logical-ddl.json','06-baseline-load':'baseline-load/load-summary.txt',
'07-logical-load':'logical-load/load-summary.txt','08-physical-equality':'physical-data-equality.json',
'09-physical-ddl':'physical-ddl.json','10-security-config':'configuration.txt',
'11-physical-load':'physical-load/load-summary.txt','12-sync-block':'sync-sync-block.txt',
'13-sync-load':'sync-load/load-summary.txt','14-security-hba':'pgcat-security.txt',
'15-pgcat-ports':'pgcat-compose-ps.txt','16-logical2-equality':'logical2-data-equality.json',
'17-pgcat-routing':'pgcat-routing.txt','18-pgcat-hurl':'pgcat-hurl.txt',
'19-pgcat-smoke':'pgcat-smoke/smoke-summary.txt','20-comparison':'comparison.txt'}
for source in sorted(R.glob('*.jpg')):
    im=Image.open(source);assert im.format=='JPEG'
    gray=im.convert('L')
    # Find printed content, disregarding the far-right scrollbar and JPEG near-white noise.
    mask=gray.point(lambda p:255 if p<150 else 0)
    box=mask.crop((0,0,im.width-24,im.height)).getbbox()
    if not box:raise ValueError(source)
    left,top,right,bottom=box
    crop=(max(0,left-14),max(0,top-12),min(im.width-24,right+14),min(im.height,bottom+14))
    if source.stem=='10-security-config':crop=(crop[0],crop[1],crop[2],min(crop[3],535))
    target=dest/(source.stem+'.png')
    im.crop(crop).save(target)
    evidence=R.parent/sources[source.stem]
    manifest.append({'source':source.name,'evidence':sources[source.stem],
      'evidenceSHA256':hashlib.sha256(evidence.read_bytes()).hexdigest(),
      'capturedFileMtimeUtc':__import__('datetime').datetime.fromtimestamp(source.stat().st_mtime,__import__('datetime').timezone.utc).isoformat(),
      'originalFormat':'JPEG','dimensions':im.size,'crop':crop,
      'sourceSHA256':hashlib.sha256(source.read_bytes()).hexdigest(),
      'output':target.name,'outputSHA256':hashlib.sha256(target.read_bytes()).hexdigest(),
      'method':'Browser capture of verified localhost evidence viewer; crop only; original JPEG preserved; PNG avoids a second lossy encoding'})
(R/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Prepared',len(manifest),'genuine screenshot crops')
