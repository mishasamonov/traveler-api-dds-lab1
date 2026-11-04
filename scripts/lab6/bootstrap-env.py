import secrets
from pathlib import Path
root=Path(__file__).resolve().parents[2]
target=root/'.env'
if target.exists():
    print('.env already exists; preserved')
else:
    text=(root/'.env.example').read_text(encoding='utf-8')
    while 'GENERATE_LOCALLY' in text:
        text=text.replace('GENERATE_LOCALLY',secrets.token_hex(24),1)
    target.write_text(text,encoding='utf-8')
    print('Created .env with independent random local passwords')
