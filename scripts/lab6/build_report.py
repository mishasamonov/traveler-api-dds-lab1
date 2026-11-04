"""Ukrainian report for laboratory 6 (Word), styles taken from the laboratory 5 report."""
import json, sys
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / 'evidence/lab6'; S = E / 'screenshots'; F = E / 'figures'
UNI = Path(r'D:/УНИВЕР/МАГІСТРАТУРА/1 СЕМЕСТР/РОЗПОДІЛЕНІ СХОВИЩА ДАНИХ')
TEMPLATE = UNI / 'Лаба 5/TravelerAPI_Lab5_Samonov.docx'
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else UNI / 'Лаба 6/TravelerAPI_Lab6_Samonov.docx'
BASE = 'https://github.com/mishasamonov/traveler-api-dds-lab1'
BRANCH = f'{BASE}/tree/lab6-sharding'
A = json.loads((E / 'analysis.json').read_text(encoding='utf-8'))
COMMITS = json.loads((E / 'commits.json').read_text(encoding='utf-8')) if (E / 'commits.json').exists() else {}


def num(v, d=1): return f'{v:,.{d}f}'.replace(',', ' ').replace('.', ',')
def ms(v, d=1): return num(v, d) + ' мс'
def pct(v, d=2): return num(v * 100, d) + ' %'


d = Document(TEMPLATE)
for el in list(d.element.body):
    if el.tag != qn('w:sectPr'): d.element.body.remove(el)
figure = 0


def text(s='', style=None, bold=False):
    p = d.add_paragraph(style=style)
    if s:
        r = p.add_run(s); r.bold = bold or None
    return p


def heading(s):
    p = d.add_heading(s, 1); p.paragraph_format.keep_with_next = True; return p


def sub(s):
    p = text(s, bold=True); p.paragraph_format.keep_with_next = True; return p


def bullet(s): return text('- ' + s)


def link(url, label):
    p = text(); p.paragraph_format.keep_together = True
    el = OxmlElement('w:hyperlink'); el.set(qn('r:id'), p.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run = OxmlElement('w:r'); pr = OxmlElement('w:rPr')
    c = OxmlElement('w:color'); c.set(qn('w:val'), '0563C1'); pr.append(c)
    u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); pr.append(u)
    run.append(pr); t = OxmlElement('w:t'); t.text = url; run.append(t); el.append(run); p._p.append(el)
    p.add_run(' — ' + label)


def image(path, caption, width=None):
    global figure
    path = Path(path); assert path.exists(), path; figure += 1
    im = Image.open(path)
    w = width or min(6.5, 8.6 * im.width / im.height)
    p = text(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(str(path), width=Inches(w)); shape._inline.docPr.set('descr', caption)
    cap = text(f'Рисунок {figure} – {caption}', 'Caption'); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return figure


def shot(name, caption, width=None): return image(S / f'{name}.png', caption, width)
def fig(name, caption, width=6.5): return image(F / f'{name}.png', caption, width)


def table(headers, rows, widths, font=11):
    t = d.add_table(rows=1, cols=len(headers)); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
    for c, s in zip(t.rows[0].cells, headers): c.text = s
    for row in rows:
        cells = t.add_row().cells
        for c, s in zip(cells, row): c.text = str(s)
    borders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        b = OxmlElement('w:' + side); b.set(qn('w:val'), 'single'); b.set(qn('w:sz'), '4'); b.set(qn('w:color'), 'A6A6A6'); borders.append(b)
    t._tbl.tblPr.append(borders)
    for ri, row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        if ri == 0: row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
        for ci, c in enumerate(row.cells):
            c.width = Inches(widths[ci]); c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if ri == 0:
                sh = OxmlElement('w:shd'); sh.set(qn('w:fill'), 'DFE9F3'); c._tc.get_or_add_tcPr().append(sh)
            for p in c.paragraphs:
                p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.keep_with_next = ri == 0
                if ci > 0: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs: r.font.size = Pt(font); r.bold = ri == 0 or None
    text().paragraph_format.space_after = Pt(0)
    return t


HERE = Path(__file__).resolve().parent
for part in ('report_a.py', 'report_perf_text.py', 'report_c.py', 'report_d.py', 'report_e.py'):
    if part == 'report_perf_text.py':
        exec((HERE / 'report_b.py').read_text(encoding='utf-8'))
        exec((HERE / 'report_b2.py').read_text(encoding='utf-8'))
    else:
        exec((HERE / part).read_text(encoding='utf-8'))
# Drop relationships left over from the template body (old links and images).
import re as _re
used = set(_re.findall(r'r:(?:id|embed|link)="(rId\d+)"', d.element.xml))
for rid, rel in list(d.part.rels.items()):
    if rid not in used and (rel.reltype.endswith('/hyperlink') or rel.reltype.endswith('/image')):
        del d.part.rels[rid]
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
d.core_properties.author = 'Самонов Михайло'
d.core_properties.title = 'Лабораторна робота 6. Секціонування'
d.save(OUTPUT)
print('REPORT', OUTPUT, 'figures', figure)
