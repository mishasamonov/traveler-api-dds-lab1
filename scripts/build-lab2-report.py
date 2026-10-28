"""Build the Ukrainian lab report from verified k6 files only. Run after all tests."""
import argparse, json
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

ROOT=Path(__file__).resolve().parent.parent
R=ROOT/'tests/performance-tests/results'
SHOTS=ROOT/'tests/performance-tests/screenshots'
BASE='https://github.com/mishasamonov/traveler-api-dds-lab1'

def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def number(value, digits=2):return f'{value:,.{digits}f}'.replace(',',' ').replace('.',',')
def count(value):return f'{value:,}'.replace(',',' ')
def pct(value):return number(value*100,2)+' %'
def ms(value):return number(value)+' мс'

def hyperlink(p,text,url):
    link=OxmlElement('w:hyperlink');link.set(qn('r:id'),p.part.relate_to(url,RT.HYPERLINK,is_external=True))
    run=OxmlElement('w:r');props=OxmlElement('w:rPr')
    font=OxmlElement('w:rFonts');font.set(qn('w:ascii'),'Arial');font.set(qn('w:hAnsi'),'Arial');props.append(font)
    color=OxmlElement('w:color');color.set(qn('w:val'),'0563C1');props.append(color)
    underline=OxmlElement('w:u');underline.set(qn('w:val'),'single');props.append(underline)
    size=OxmlElement('w:sz');size.set(qn('w:val'),'19');props.append(size)
    run.append(props);t=OxmlElement('w:t');t.text=text;run.append(t);link.append(run);p._p.append(link)

def paragraph(doc,text='',style=None):
    p=doc.add_paragraph(text,style);return p

def heading(doc,text,level=1):return doc.add_heading(text,level)
def page(doc,title):
    p=heading(doc,title);p.paragraph_format.page_break_before=True

def table(doc,headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for c,w in zip(t.columns,widths):c.width=Inches(w)
    for c,s in zip(t.rows[0].cells,headers):c.text=s
    for row in rows:
        cells=t.add_row().cells
        for c,s in zip(cells,row):c.text=str(s)
    props=t._tbl.tblPr
    borders=OxmlElement('w:tblBorders')
    for side in ('top','left','bottom','right','insideH','insideV'):
        b=OxmlElement('w:'+side);b.set(qn('w:val'),'single');b.set(qn('w:sz'),'4');b.set(qn('w:color'),'D9D9D9');borders.append(b)
    props.append(borders)
    for ri,row in enumerate(t.rows):
        no_split=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(no_split)
        if ri==0:row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
        for ci,c in enumerate(row.cells):
            c.width=Inches(widths[ci]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=c._tc.get_or_add_tcPr();margin=OxmlElement('w:tcMar')
            for side in ('top','left','bottom','right'):
                m=OxmlElement('w:'+side);m.set(qn('w:w'),'85');m.set(qn('w:type'),'dxa');margin.append(m)
            tcpr.append(margin)
            if ri==0:
                shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'DFE9F3');tcpr.append(shade)
            for p in c.paragraphs:
                p.paragraph_format.space_before=Pt(0);p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=1.05
                p.paragraph_format.keep_with_next=ri<len(t.rows)-1
                if ci>0 or headers[0]=='VU':p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:run.font.size=Pt(10.2);run.bold=ri==0
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t

def image(doc,path,caption,width=6.85):
    p=doc.add_paragraph();p.paragraph_format.keep_with_next=True;p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after=Pt(3)
    shape=p.add_run().add_picture(str(path),width=Inches(width));shape._inline.docPr.set('descr',caption)
    cap=doc.add_paragraph(caption,'Caption');cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
    return cap

def main(output):
    names=('smoke','load','stress','spike','endurance')
    sums={name:load(R/f'{name}-summary.json')['metrics'] for name in names}
    data={name:load(R/f'{name}-analysis.json') for name in names[1:]}
    commits=load(R/'commits.json')
    d=Document();s=d.sections[0]
    s.page_width=Inches(8.5);s.page_height=Inches(11)
    s.top_margin=s.bottom_margin=Inches(.65);s.left_margin=s.right_margin=Inches(.75)
    normal=d.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(11)
    normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.05
    for name,size in [('Title',18),('Subtitle',12),('Heading 1',13.5),('Caption',9.5)]:
        style=d.styles[name];style.font.name='Arial';style.font.size=Pt(size)
        style.font.color.rgb=RGBColor(0,0,0);style.paragraph_format.space_after=Pt(6)
        if name=='Heading 1':
            style.paragraph_format.space_before=Pt(8);style.paragraph_format.keep_with_next=True
        if name=='Caption':style.font.bold=False
    d.settings.element.append(OxmlElement('w:doNotAutoCompressPictures'))
    footer=s.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    d.core_properties.title='Лабораторна робота 2 Тестування TravelerAPI з k6'
    d.core_properties.author='Самонов Михайло';d.core_properties.subject='Розподілені сховища даних'

    paragraph(d,'Лабораторна робота 2','Title')
    paragraph(d,'Тестування продуктивності TravelerAPI з k6','Subtitle')
    paragraph(d,'Самонов Михайло  •  ІН.м-62/2')
    paragraph(d,'Мета роботи — перевірити, як TravelerAPI працює під різним навантаженням, і зберегти результати для наступних лабораторних.')
    heading(d,'Підготовка')
    paragraph(d,'Використав API з першої лабораторної, його код і схему БД не змінював. Тести запускав у Windows на ноутбуці з Intel Core i5-11300H та 15,79 ГБ RAM. Node.js 22.18.0, PostgreSQL 16.15 і k6 2.3.0 працювали на цьому ж комп’ютері, без Docker.')
    paragraph(d,'Перед кожним тестом готував 2 000 планів і по 3 локації на план. Кожен віртуальний користувач (VU) редагував свій план: 8 читань, 2 оновлення з version і п’ять пауз по 100 мс за цикл. Кожен десятий цикл також створював і видаляв тимчасовий план із локацією.')
    paragraph(d,'Тести виконував по черзі. Орієнтувався на p95 менше 500 мс і частку неочікуваних HTTP помилок менше 1 %. p95 — час, у який вкладаються 95 % запитів. За повільніших відповідей користувачі встигають зробити менше запитів.')

    heading(d,'1 Smoke')
    sm=sums['smoke']
    paragraph(d,'Адаптував сценарій викладача під свої endpoint-и й запустив короткий тест на 20 секунд із максимум 5 VU. Перевірив створення, читання, зміну та видалення даних. Зміна локації з актуальною version проходить, зі старою повертає 409, а повторна спроба з новою версією знову проходить.')
    paragraph(d,f'Виконано {count(sm["http_reqs"]["values"]["count"])} запити та {count(sm["checks"]["values"]["passes"])} перевірки без помилок. Отримано {count(sm["expected_version_conflicts"]["values"]["count"])} очікувані конфлікти версій; p95 — {ms(sm["http_req_duration"]["values"]["p(95)"])}.')
    image(d,SHOTS/'01-smoke.png','Рисунок 1  Результати smoke тесту')

    page(d,'2 Load')
    top=data['load']['stable_plateaus']['load200']
    paragraph(d,'Поступово збільшував навантаження: 25, 50, 100 і 200 VU. Кожен рівень утримував 30 секунд. Для порівняння брав сталі частини цих періодів без перших і останніх 5 секунд.')
    paragraph(d,f'При 200 VU середній час відповіді становив {ms(top["avg_ms"])}, p95 — {ms(top["p95_ms"])}, потік — {number(top["rps"],1)} запитів за секунду. HTTP помилок не було. Отже, 200 VU — найбільше успішно перевірене навантаження за обраним критерієм на цьому комп’ютері.')
    image(d,SHOTS/'02-load.png','Рисунок 2  Результати load тесту')
    image(d,R/'load-chart.png','Рисунок 3  Зміна навантаження і часу відповіді',width=6.0)

    page(d,'3 Stress')
    stress=data['stress']['stable_plateaus']
    paragraph(d,'Збільшував навантаження від 200 до 500, 1 000 і 2 000 VU, утримуючи кожен рівень 45 секунд. Потім зменшив його до 20 VU, щоб перевірити відновлення.')
    paragraph(d,f'При 500 VU p95 вже перевищив 500 мс і становив {ms(stress["stress500"]["p95_ms"])}. При 2 000 VU він зріс до {ms(stress["stress2000"]["p95_ms"])} — вище прийнятої межі 2 секунд. API не зупинився, HTTP помилок не було. Позначка FAIL у k6 означає перевищення порога затримки.')
    image(d,SHOTS/'03-stress.png','Рисунок 4  Результати stress тесту')
    paragraph(d,f'Після спаду навантаження p95 повернувся нижче 500 мс приблизно за {number(data["stress"]["recovery"]["seconds_after_nominal_down_end"],1)} с. На сталому відрізку відновлення він становив {ms(stress["recovery"]["p95_ms"])}.')
    image(d,R/'stress-chart.png','Рисунок 5  Перевантаження та відновлення API',width=6.0)

    page(d,'4 Spike')
    spike=data['spike']['stable_plateaus']
    paragraph(d,'За 1 секунду збільшив навантаження з 20 до 1 000 VU, утримував сплеск 30 секунд і за 1 секунду повернувся до 20 VU. Поточні ітерації могли завершуватися ще до 30 секунд.')
    paragraph(d,f'На піку p95 становив {ms(spike["spike"]["p95_ms"])}. Усього виконано {count(sums["spike"]["http_reqs"]["values"]["count"])} запитів без HTTP помилок і перерваних ітерацій. Окремо збереження кожного запису цей тест не перевіряв.')
    image(d,SHOTS/'04-spike.png','Рисунок 6  Результати spike тесту')
    paragraph(d,f'Після сплеску p95 повернувся нижче 500 мс приблизно за {number(data["spike"]["recovery"]["seconds_after_nominal_down_end"],1)} с; на сталому відрізку відновлення — {ms(spike["recovery"]["p95_ms"])}. Час відновлення у stress і spike оцінював із кроком 5 с, за трьома послідовними успішними інтервалами.')
    image(d,R/'spike-chart.png','Рисунок 7  Реакція API на різкий сплеск',width=6.0)

    page(d,'5 Endurance')
    e=data['endurance'];em=sums['endurance']
    paragraph(d,'Запустив тест на 25 VU з постійним навантаженням протягом 30 хвилин. Разом із розгоном і завершенням по 30 секунд він тривав 31 хвилину.')
    image(d,SHOTS/'06-endurance-start.png','Рисунок 8  Початок endurance тесту')
    paragraph(d,f'За весь запуск виконано {count(em["http_reqs"]["values"]["count"])} запитів без HTTP помилок. Усі перевірки пройдені.')
    image(d,SHOTS/'05-endurance.png','Рисунок 9  Підсумок endurance тесту')
    p=paragraph(d,f'Тест завершився за 31 хв 00,2 с: {count(em["iterations"]["values"]["count"])} повних ітерацій, перерваних немає.')
    p.paragraph_format.keep_with_next=True
    image(d,SHOTS/'07-endurance-finish.png','Рисунок 10  Завершення endurance тесту')
    mem=e['api_memory']
    paragraph(d,f'p95 перших п’яти хвилин сталого навантаження — {ms(e["first_5min"]["p95_ms"])}, останніх — {ms(e["last_5min"]["p95_ms"])}. Медіана приватної пам’яті API за ці періоди становила {number(mem["first_5min_median_mb"],1)} і {number(mem["last_5min_median_mb"],1)} МБ. За цей запуск поступового погіршення не виявив; для перевірки витоків пам’яті потрібен довший тест.')
    image(d,R/'endurance-chart.png','Рисунок 11  Час відповіді та пам’ять під час endurance',width=6.0)

    heading(d,'6 Додаткові завдання')
    paragraph(d,'Налаштував автоматичний smoke тест у GitHub Actions і збереження HTML звітів та JSON метрик. Зібрані дані використав для графіків у звіті. CI перевіряє працездатність API, його швидкодію з локальними тестами не порівнював.')
    paragraph(d,'Після налаштування середовища CI також пройшли 56 HTTP запитів Hurl і три тести конкурентного доступу.')
    image(d,SHOTS/'08-ci-hurl.png','Рисунок 12  Тести Hurl у GitHub Actions')
    image(d,SHOTS/'09-ci-concurrency.png','Рисунок 13  Тести конкурентного доступу')

    heading(d,'Висновок')
    paragraph(d,'API витримав 200 VU з p95 менше 500 мс. При перевантаженні затримки зросли, але після спаду навантаження робота відновилася. За 30 хвилин при 25 VU помилок і погіршення не виявив. Тимчасових даних після тестів не залишилося.')
    heading(d,'Посилання')
    links=[
        (BASE+'/tree/lab2-performance','Код лабораторної та результати тестів'),
        (BASE+'/commit/'+commits['smoke'],'Початковий коміт зі smoke тестом'),
        (BASE+'/commit/'+commits['endurance'],'Коміт із 30-хвилинним тестом'),
    ]
    for url,label in links:
        p=paragraph(d);hyperlink(p,url,url)
        p.add_run(' — '+label).font.size=Pt(10.2)
        p.paragraph_format.space_after=Pt(4)
        p.paragraph_format.keep_together=True
    for root in (d.element,d.styles.element):
        for border in list(root.xpath('.//w:pBdr')):border.getparent().remove(border)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);d.save(output)
    print(output)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    main(parser.parse_args().output)
