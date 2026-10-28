"""Crop empty margins from genuine captures without resampling or editing pixels."""
from pathlib import Path
from PIL import Image,ImageChops
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parent.parent
SHOTS=ROOT/'evidence/screenshots'
SOURCES={
 '02-compose-ps':'evidence/compose-ps.txt','03-web-logs':'evidence/web-logs-follow.txt',
 '04-docker-stats':'evidence/docker-stats-load.txt','05-hurl':'evidence/hurl-result.txt',
 '06-concurrency':'evidence/concurrency.txt','07-smoke':'tests/performance-tests/results-docker/smoke-summary.txt',
 '08-load':'tests/performance-tests/results-docker/load-summary.txt','09-stress':'tests/performance-tests/results-docker/stress-summary.txt',
 '10-spike':'tests/performance-tests/results-docker/spike-summary.txt','11-endurance-start':'evidence/endurance-start.txt',
 '12-endurance-finish':'evidence/endurance-finish.txt','13-endurance':'tests/performance-tests/results-docker/endurance-summary.txt',
 '14-ci':'evidence/ci-result.txt','15-persistence':'evidence/persistence.txt','16-health':'evidence/health.txt'}
out=SHOTS/'crops';out.mkdir(exist_ok=True)
for src in sorted(SHOTS.glob('*.jpg')):
 im=Image.open(src).convert('RGB');assert Image.open(src).format=='JPEG'
 difference=ImageChops.difference(im,Image.new('RGB',im.size,'white')).convert('L').point(lambda p:255 if p>65 else 0)
 bbox=difference.getbbox()
 box=(max(0,bbox[0]-12),max(0,bbox[1]-12),min(im.width,bbox[2]+12),min(im.height,bbox[3]+12))
 target=out/(src.stem+'.png');im.crop(box).save(target)
 source=ROOT/SOURCES[src.stem]
 meta={'sourceFile':SOURCES[src.stem],'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
  'captureFile':src.name,'captureSha256':hashlib.sha256(src.read_bytes()).hexdigest(),
  'outputSha256':hashlib.sha256(target.read_bytes()).hexdigest(),'originalFormat':'JPEG',
  'method':'Genuine browser screenshot of saved command output; whitespace crop saved as PNG, no resampling or text reconstruction','crop':box}
 (out/(src.stem+'-capture.json')).write_text(json.dumps(meta,indent=2),encoding='utf-8')
 print(src.stem,im.size,'->',box)
native=SHOTS/'01-docker-desktop-full.png'
if native.exists():
 im=Image.open(native);assert im.format=='PNG'
 # Preserve the returned table, excluding the pointer in the expansion column.
 target=out/'01-docker-desktop.png';im.crop((500,395,1580,600)).save(target)
 (out/'01-docker-desktop-capture.json').write_text(json.dumps({'captureFile':native.name,
  'captureSha256':hashlib.sha256(native.read_bytes()).hexdigest(),'outputSha256':hashlib.sha256(target.read_bytes()).hexdigest(),
  'originalFormat':'PNG','method':'Native ShareX ActiveWindow capture; lossless table crop excluding pointer; no resampling','crop':[500,395,1580,600]},indent=2),encoding='utf-8')
