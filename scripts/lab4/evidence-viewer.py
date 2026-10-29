"""Read-only local evidence viewer. Never executes commands or changes source files."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import html,textwrap,json
ROOT=Path(__file__).resolve().parents[2]
FILES={}
for mode in ['baseline','logical','physical','sync','two','pgcat','logical2']:
 for kind in ['hurl','replication','security','subscriptions','compose-ps','routing','sync-block','ddl','data-equality']:
  ext='json' if kind in ['ddl','data-equality'] else 'txt'
  FILES[f'{mode}-{kind}']=f'evidence/lab4/{mode}-{kind}.{ext}'
 for scenario in ['smoke','load','read']:
  FILES[f'{mode}-{scenario}']=f'evidence/lab4/{mode}-{scenario}/{scenario}-summary.txt'
FILES['configuration']='evidence/lab4/configuration.txt'
FILES['comparison']='evidence/lab4/comparison.txt'
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  key=parse_qs(urlparse(self.path).query).get('view',['baseline-hurl'])[0]
  if key not in FILES:self.send_error(404);return
  p=ROOT/FILES[key]
  body=p.read_text(encoding='utf-8-sig') if p.exists() else 'Evidence has not been collected yet'
  if key.endswith('-data-equality') and p.exists():
   value=json.loads(body)
   body='\n\n'.join(node+'\n'+'\n'.join(f'{k}: {v}' for k,v in row.items()) for node,row in value.items())
  if key.endswith('-replication'):
   body=body.split('\n{')[0]
   body='\n'.join(line for line in body.splitlines() if line.strip())
  query=parse_qs(urlparse(self.path).query)
  if 'start' in query:body='\n'.join(body.splitlines()[int(query['start'][0]):int(query['start'][0])+18])
  if key=='configuration':body=body.split('\npgcat/')[0]
  body='\n'.join(textwrap.fill(s,width=105,break_long_words=False,break_on_hyphens=False) if len(s)>105 else s for s in body.splitlines())
  page=f'''<!doctype html><meta charset="utf-8"><title>Lab 4 {html.escape(key)}</title>
  <style>body{{margin:28px 36px;font-family:Arial;color:#111;background:#fff}}h1{{font-size:27px;margin:0 0 7px}}p{{font-size:17px;color:#555;margin:0 0 18px}}pre{{font:23px/1.3 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin:0;max-width:1660px}}</style>
  <h1>TravelerAPI Laboratory 4 · {html.escape(key)}</h1><p>Saved original evidence · {html.escape(FILES[key])}</p><pre>{html.escape(body)}</pre>'''
  b=page.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def log_message(self,*args):pass
ThreadingHTTPServer(('127.0.0.1',8768),Handler).serve_forever()
