"""Screenshots for the report: saved command outputs in a terminal window and
source files in an editor window, rendered by headless Microsoft Edge.
Text is taken verbatim from evidence/lab6 and the repository; nothing is retyped."""
import html, json, re, subprocess, sys
from pathlib import Path
from PIL import Image
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / 'evidence/lab6'
SHOTS = E / 'screenshots'; SHOTS.mkdir(parents=True, exist_ok=True)
HTML = ROOT / '.runtime/lab6/shots'; HTML.mkdir(parents=True, exist_ok=True)
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
ANSI = {'1;32': 'color:#16c60c;font-weight:bold', '1;31': 'color:#e74856;font-weight:bold', '1': 'font-weight:bold',
        '1;33': 'color:#f9f1a5;font-weight:bold', '1;34': 'color:#3b78ff;font-weight:bold', '1;36': 'color:#61d6d6;font-weight:bold',
        '32': 'color:#16c60c', '31': 'color:#e74856', '33': 'color:#c19c00', '36': 'color:#3a96dd', '34': 'color:#3b78ff', '90': 'color:#767676'}


def ansi(text):
    out, open_ = [], 0
    for part in re.split(r'(\x1b\[[0-9;]*m)', text):
        m = re.fullmatch(r'\x1b\[([0-9;]*)m', part)
        if not m: out.append(html.escape(part)); continue
        code = m.group(1)
        if code in ('', '0'):
            out.append('</span>' * open_); open_ = 0
        elif code in ANSI:
            out.append(f'<span style="{ANSI[code]}">'); open_ += 1
    return ''.join(out) + '</span>' * open_


def render(name, body, width):
    page = HTML / f'{name}.html'
    page.write_text(body, encoding='utf-8')
    lines = body.count('\n') + 10
    out = SHOTS / f'{name}.png'
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1.5',
                    f'--window-size={width},{min(9000, 120 + lines * 22)}', f'--screenshot={out}', page.as_uri()],
                   check=True, capture_output=True)
    im = Image.open(out).convert('RGB')
    # Trim the unused page below the window frame (page background is pure white).
    bg = Image.new('RGB', im.size, (255, 255, 255))
    from PIL import ImageChops
    box = ImageChops.difference(im, bg).getbbox()
    im.crop((0, 0, im.width, min(im.height, box[3] + 18))).save(out, optimize=True)
    print('shot', out.name, im.size)


FRAME = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;padding:14px;background:#fff;font-family:'Segoe UI',sans-serif}
.win{border-radius:8px;overflow:hidden;box-shadow:0 4px 18px rgba(0,0,0,.35);border:1px solid #3a3a3a;display:inline-block;min-width:calc(100% - 4px)}
.bar{background:#2b2b2b;color:#ddd;font-size:13px;padding:7px 12px;display:flex;align-items:center;gap:10px}
.tab{background:#0c0c0c;padding:5px 14px;border-radius:6px 6px 0 0;color:#fff}
.dots{margin-left:auto;letter-spacing:14px;color:#aaa}
pre{margin:0;padding:12px 16px;background:#0c0c0c;color:#cccccc;font:14.5px/1.42 'Cascadia Mono',Consolas,monospace;white-space:pre}
.p{color:#16c60c}.c{color:#f9f1a5}
.ed{background:#1f1f1f}.edbar{background:#181818;color:#ccc;font-size:13px;padding:0;display:flex}
.edtab{background:#1f1f1f;border-top:2px solid #0078d4;padding:7px 16px;color:#fff}
.crumb{background:#1f1f1f;color:#a0a0a0;font-size:12.5px;padding:4px 16px;border-bottom:1px solid #2b2b2b}
.ed pre{background:#1f1f1f;color:#d4d4d4}
.ln{color:#6e7681;flex:0 0 3.2em;text-align:right;margin-right:1.2em}
.row{display:flex}.src{white-space:pre-wrap;word-break:break-word;flex:1}
.ed pre{white-space:normal}
@@CSS@@
</style><body>@@BODY@@</body>"""


def terminal(name, blocks, title='Terminal', width=1180):
    """blocks: list of (command, output). Prompt uses the real project folder."""
    parts = []
    for command, output in blocks:
        if command is not None:
            parts.append(f'<span class="p">traveler-api-lab6&gt;</span> <span class="c">{html.escape(command)}</span>\n')
        parts.append(ansi(output.rstrip('\n')) + '\n')
    body = f'<div class="win"><div class="bar"><span class="tab">&#9654; {html.escape(title)}</span><span class="dots">&#8212; &#9633; &#10005;</span></div><pre>{"".join(parts).rstrip()}</pre></div>'
    render(name, FRAME.replace('@@CSS@@', '').replace('@@BODY@@', body), width)


def code(name, path, start=1, end=None, width=1180, mark=None):
    source = (ROOT / path).read_text(encoding='utf-8').splitlines()
    end = end or len(source)
    snippet = '\n'.join(source[start - 1:end])
    lexer = get_lexer_for_filename(path)
    fmt = HtmlFormatter(style='github-dark', nowrap=True)
    lines = highlight(snippet, lexer, fmt).rstrip('\n').split('\n')
    numbered = ''.join(f'<div class="row"><span class="ln">{start + i}</span><span class="src">{l or " "}</span></div>' for i, l in enumerate(lines))
    crumb = ' &rsaquo; '.join(html.escape(p) for p in ['traveler-api-lab6', *Path(path).parts])
    body = (f'<div class="win ed"><div class="bar"><span>traveler-api-lab6 &#8212; branch lab6-sharding</span><span class="dots">&#8212; &#9633; &#10005;</span></div>'
            f'<div class="edbar"><span class="edtab">{html.escape(Path(path).name)}</span></div><div class="crumb">{crumb}</div><pre>{numbered}</pre></div>')
    render(name, FRAME.replace('@@CSS@@', fmt.get_style_defs('.ed pre')).replace('@@BODY@@', body), width)


def read(name): return (E / name).read_text(encoding='utf-8')


def lines_of(path, needle_start, needle_end=None):
    src = (ROOT / path).read_text(encoding='utf-8').splitlines()
    a = next(i for i, l in enumerate(src) if needle_start in l) + 1
    b = next(i for i, l in enumerate(src) if i >= a and needle_end in l) + 1 if needle_end else len(src)
    return a, b
