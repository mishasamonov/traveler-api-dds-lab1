"""Laboratory 7: add the monitoring secrets to the local .env (random values).
Existing keys are preserved, so the laboratory 6 passwords stay the same."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[2]
target = root / '.env'
if not target.exists():
    text = (root / '.env.example').read_text(encoding='utf-8')
    while 'GENERATE_LOCALLY' in text:
        text = text.replace('GENERATE_LOCALLY', secrets.token_hex(24), 1)
    target.write_text(text, encoding='utf-8')
    print('Created .env from .env.example')
present = {line.split('=', 1)[0] for line in target.read_text(encoding='utf-8').splitlines() if '=' in line}
wanted = {'MONITOR_USER': 'lab7_monitor', 'MONITOR_PASSWORD': secrets.token_hex(24),
          'GRAFANA_ADMIN_PASSWORD': secrets.token_hex(16), 'GRAFANA_PORT': '3000', 'PROMETHEUS_PORT': '9090'}
added = [f'{k}={v}' for k, v in wanted.items() if k not in present]
if added:
    with target.open('a', encoding='utf-8') as f:
        f.write('# Laboratory 7: monitoring\n' + '\n'.join(added) + '\n')
print('Added to .env:', ', '.join(a.split('=')[0] for a in added) or 'nothing (already present)')
