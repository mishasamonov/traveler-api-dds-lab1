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
COMMITS={
 'smoke':'2701b0997fb4a56d72c3bb83efac98c4004e4ca8',
 'load':'c0a05e1e4252de6c43aa08353eec41606c21690f',
 'stress':'6d7089ca32fb7e9ea97b437ea1b686f354278ce6',
 'spike':'a29825981078ee352d06ecddaaa297a8420abd54',
 'ci':'11adce763332e3aca928fa617624363404405166',
}

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
                if ci>0 or headers[0]=='VU':p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:run.font.size=Pt(10.2);run.bold=ri==0
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t

def image(doc,path,caption,width=6.85):
    p=doc.add_paragraph();p.paragraph_format.keep_with_next=True;p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    shape=p.add_run().add_picture(str(path),width=Inches(width));shape._inline.docPr.set('descr',caption)
    cap=doc.add_paragraph(caption,'Caption');cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
    return cap

def screenshot(doc,name,number_,caption):
    image(doc,SHOTS/f'{name}.png',f'Рисунок {number_}  {caption}')

def commit(links,key,label):
    links.append((f'{BASE}/commit/{COMMITS[key]}',label))

def metrics(doc,summary):
    m=summary['metrics'];return table(doc,['Запити','Середній час','p95','HTTP помилки'],[[count(m['http_reqs']['values']['count']),ms(m['http_req_duration']['values']['avg']),ms(m['http_req_duration']['values']['p(95)']),pct(m['http_req_failed']['values']['rate'])]],[1.3,1.8,1.7,2.2])

def main(output):
    links=[]
    sums={n:load(R/f'{n}-summary.json') for n in ('smoke','load','stress','spike','endurance')}
    data={n:load(R/f'{n}-analysis.json') for n in ('load','stress','spike','endurance')}
    env=load(R/'environment.json');ci=load(R/'ci-proof.json')
    meta=R/'commits.json'
    if meta.exists():COMMITS.update(load(meta))
    if 'endurance' not in COMMITS:raise RuntimeError('Record the endurance commit before building the report')
    for name in data:
        if not (R/f'{name}-chart.png').exists():raise FileNotFoundError(f'Generate {name}-chart.png first')
    d=Document();s=d.sections[0]
    s.page_width=Inches(8.5);s.page_height=Inches(11)
    s.top_margin=Inches(.65);s.bottom_margin=Inches(.65);s.left_margin=Inches(.75);s.right_margin=Inches(.75)
    normal=d.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(11)
    normal.paragraph_format.space_after=Pt(7);normal.paragraph_format.line_spacing=1.08
    for name,size in [('Title',20),('Subtitle',13),('Heading 1',15),('Heading 2',12),('Caption',9.5)]:
        style=d.styles[name];style.font.name='Arial';style.font.size=Pt(size);style.font.color.rgb=RGBColor(0,0,0)
        style.paragraph_format.space_after=Pt(7)
        if name.startswith('Heading'):style.paragraph_format.space_before=Pt(10);style.paragraph_format.keep_with_next=True
    settings=d.settings.element;settings.append(OxmlElement('w:doNotAutoCompressPictures'))
    footer=s.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=footer.add_run();r.font.size=Pt(9);field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');r._r.addnext(field)
    d.core_properties.title='Лабораторна робота 2 Тестування продуктивності TravelerAPI з k6'
    d.core_properties.author='Самонов Михайло';d.core_properties.subject='Розподілені сховища даних'

    paragraph(d,'Лабораторна робота 2','Title')
    paragraph(d,'Тестування продуктивності TravelerAPI з k6','Subtitle')
    paragraph(d,'Самонов Михайло  •  ІН.м-62/2')
    paragraph(d,'Мета роботи - перевірити продуктивність TravelerAPI за допомогою k6: як API працює під звичайним навантаженням, під час перевантаження, різкого сплеску та протягом 30 хвилин. Ці результати будуть основою для порівняння в наступних лабораторних.')
    links.append((BASE+'/tree/lab2-performance','Репозиторій роботи, гілка lab2-performance'))
    heading(d,'1 Середовище та методика')
    table(d,['Компонент','Конфігурація'],[
        ['Комп’ютер','Intel Core i5-11300H, 8 логічних процесорів, 15,79 ГБ RAM'],
        ['Система','Windows, збірка '+env['release']],
        ['API','Node.js '+env['node']+', Express 5, один процес; порт 4567'],
        ['База даних','PostgreSQL 16.15, нативний процес; 127.0.0.1:55432'],
        ['Параметри БД','READ COMMITTED, пул API 20, shared_buffers 128 МБ'],
        ['Генератор','Grafana k6 2.3.0; той самий комп’ютер, без Docker і VM'],
    ],[1.55,5.45])
    paragraph(d,'Перед кожним тестом відновлював однаковий набір: 2 000 планів і по 3 локації на план. Дані готуються до вимірювання; кожен VU редагує власний план. Звичайний цикл містить 8 читань і 2 оновлення з version та п’ять пауз по 100 мс. Кожен десятий цикл також створює тимчасовий план і локацію та видаляє план.')
    paragraph(d,'Критерій прийнятної роботи: p95 < 500 мс, неочікувані HTTP помилки < 1 %. p95 означає час, швидше якого завершилися 95 % запитів. Вимірюється закрита модель користувачів: при зростанні затримки фактичний потік запитів може зменшуватися. Тести виконував послідовно, по одному запуску; k6, API та БД ділять ресурси комп’ютера.')
    table(d,['Тест','Профіль'],[
        ['Smoke','20 с, максимум 5 VU'],['Load','25 → 50 → 100 → 200 VU; плато по 30 с'],
        ['Stress','200 → 500 → 1 000 → 2 000 VU; плато по 45 с; відновлення 20 VU'],
        ['Spike','20 → 1 000 за 1 с, сплеск 30 с, спад до 20 за 1 с'],
        ['Endurance','25 VU протягом 1 800 с; додатково по 30 с розгін і завершення'],
    ],[1.55,5.45])

    page(d,'2 Базовий запуск і перевірка версій')
    commit(links,'smoke','Smoke — коміт із базовим тестом')
    paragraph(d,'Адаптував конфігурацію endpoint-ів і клієнт із наданого викладачем проєкту. Оригінальні файли та MIT ліцензія збережені в instructor. Для генератора даних прибрав зовнішнє завантаження двох допоміжних функцій, тому під час тесту k6 не залежить від віддалених JavaScript модулів.')
    paragraph(d,'API запускав локально на порту 4567. Команда запуску тесту:')
    links.append(('http://127.0.0.1:4567','Локальна адреса API, працює після запуску сервера'))
    p=paragraph(d,'k6 run tests/performance-tests/smoke-test.js');p.runs[0].font.name='Consolas';p.runs[0].font.size=Pt(10)
    metrics(d,sums['smoke'])
    sm=sums['smoke']['metrics'];conf=sm['expected_version_conflicts']['values']['count'];checks=sm['checks']['values']
    paragraph(d,f'Пройдено {count(checks["passes"])} перевірки, невдалих - {checks["fails"]}. У {count(conf)} циклах підтверджено захист локації від застарілого оновлення. Очікувані 409 і 404 задані для конкретних запитів через responseCallback; інші статуси залишаються помилками.')
    heading(d,'Послідовність перевірки локації',2)
    for text in [
        'Створив локацію з version = 1 та оновив notes із цією версією. Відповідь 200 повернула version = 2.',
        'Повторив оновлення з version = 1. API повернув 409; повторне читання підтвердило, що попередні notes збережені.',
        'Повторив потрібну зміну з актуальною version = 2 та отримав 200. Після цього перевірив видалення локації, плану та очікуваний 404.',
    ]:paragraph(d,text,'List Number')
    p=paragraph(d,'{ version: location.version, notes: "k6 edited location" }');p.runs[0].font.name='Consolas';p.runs[0].font.size=Pt(10)
    paragraph(d,'Реалізацію API та схему з першої лабораторної не змінював. Адаптація другої роботи стосується тестового клієнта: він передає актуальні версії і перевіряє конфлікти. Окремо локально пройшли 3 наявні тести конкурентного доступу.')
    heading(d,'Збережений вивід k6',2)
    for line in [f'http_reqs: {sm["http_reqs"]["values"]["count"]}',f'http_req_failed: {sm["http_req_failed"]["values"]["rate"]}',f'http_req_duration p(95): {sm["http_req_duration"]["values"]["p(95)"]:.5f} ms',f'checks: {checks["passes"]} passed, {checks["fails"]} failed',f'expected_version_conflicts: {conf}']:
        p=paragraph(d,line);p.paragraph_format.space_after=Pt(2);p.runs[0].font.name='Consolas';p.runs[0].font.size=Pt(10)
    links.append((BASE+'/blob/lab2-performance/tests/performance-tests/results/smoke-dashboard.html','HTML звіт smoke у репозиторії'))

    page(d,'3 Навантажувальне тестування Load')
    commit(links,'load','Load — коміт із навантажувальним тестом')
    paragraph(d,'Навантаження підвищував поетапно до 200 одночасних користувачів. Нижче наведені вимірювання сталих частин плато: перші й останні 5 секунд кожного плато відкинуті, щоб зменшити вплив переходів.')
    plateaus=data['load']['stable_plateaus']
    table(d,['VU','Середній час','p95','Запитів за с','Помилки'],[[r['target_vus'],ms(r['avg_ms']),ms(r['p95_ms']),number(r['rps'],1),pct(r['failure_rate'])] for r in plateaus.values()],[.65,1.8,1.65,1.5,1.4])
    image(d,R/'load-chart.png','Рисунок 1  Затримки та потік запитів під час Load тесту')
    top=plateaus['load200']
    paragraph(d,f'При 200 одночасних користувачах API вклався в задані межі: середній час відповіді - {ms(top["avg_ms"])}, p95 - {ms(top["p95_ms"])}, помилок - {pct(top["failure_rate"])}. Це найбільше успішно перевірене навантаження для цього сценарію на моєму комп’ютері. Точну межу між 200 і наступним невдалим рівнем окремо не шукав.')

    page(d,'4 Стресове тестування Stress')
    commit(links,'stress','Stress — коміт зі стресовим тестом')
    paragraph(d,'Стресовий профіль підвищує навантаження до 2 000 VU, а потім зменшує його до 20 VU. Деградацією вважаю перевищення p95 500 мс. Операційну межу відмови визначив як p95 ≥ 2 000 мс або HTTP помилки ≥ 1 %; повне припинення роботи оцінюю окремо.')
    plateaus=data['stress']['stable_plateaus']
    table(d,['VU','Середній час','p95','Запитів за с','Помилки'],[[r['target_vus'],ms(r['avg_ms']),ms(r['p95_ms']),number(r['rps'],1),pct(r['failure_rate'])] for k,r in plateaus.items() if k!='recovery'],[.65,1.8,1.65,1.5,1.4])
    image(d,R/'stress-chart.png','Рисунок 2  Деградація та відновлення під час Stress тесту')
    failing=[r for k,r in plateaus.items() if k!='recovery' and r['p95_ms']>=500]
    breaking=[r for k,r in plateaus.items() if k!='recovery' and (r['p95_ms']>=2000 or r['failure_rate']>=.01)]
    recovery=plateaus['recovery'];rec=data['stress']['recovery']['seconds_after_nominal_down_end']
    paragraph(d,f'Перший перевірений деградований рівень - {failing[0]["target_vus"]} VU. Операційна межа за обраним критерієм досягнута на {breaking[0]["target_vus"]} VU. Повної відмови процесу та HTTP помилок у цьому запуску не виявлено. Код k6 99 означає, що поріг затримки не виконано.')
    paragraph(d,f'Сталий фрагмент відновлення: p95 {ms(recovery["p95_ms"])} після 30 с graceful завершення та 5 с стабілізації. Повернення до SLO - приблизно {number(rec,1)} с після спаду, з кроком оцінки 5 с.')

    page(d,'5 Тестування сплеску Spike')
    commit(links,'spike','Spike — коміт із тестом сплеску')
    paragraph(d,'Після сталого рівня 20 VU за 1 секунду підвищував навантаження до 1 000 VU, утримував його 30 секунд і за 1 секунду повертав до 20 VU. Активним ітераціям дозволено завершитися протягом gracefulRampDown 30 с. Сталу частину відновлення в таблиці виміряно після цього інтервалу та ще 5 с стабілізації; графік показує весь перехід.')
    plateaus=data['spike']['stable_plateaus']
    table(d,['Фаза','VU','Середній час','p95','Помилки'],[[{'before':'До сплеску','spike':'Сплеск','recovery':'Відновлення'}[k],r['target_vus'],ms(r['avg_ms']),ms(r['p95_ms']),pct(r['failure_rate'])] for k,r in plateaus.items()],[1.45,.6,1.8,1.65,1.5])
    image(d,R/'spike-chart.png','Рисунок 3  Реакція API на короткий сплеск навантаження')
    sp=sums['spike']['metrics'];rec=data['spike']['recovery']['seconds_after_nominal_down_end']
    paragraph(d,f'За час тесту виконано {count(sp["http_reqs"]["values"]["count"])} запитів без неочікуваних HTTP помилок. Усі перевірки пройдені, перерваних ітерацій немає. Втрат запитів за журналом k6 не виявлено; збереження кожного окремого запису додатково не перевіряв.')
    paragraph(d,f'Після сплеску система повернулася до обраного SLO приблизно через {number(rec,1)} с після заданого спаду, з роздільністю 5 с. Критерій відновлення - перше з трьох послідовних 5-секундних вікон з p95 < 500 мс і помилками < 1 %. Після тесту перевірка БД знову показала 2 000 планів, 6 000 локацій і відсутність залишених тимчасових планів.')

    page(d,'6 Тривале тестування Endurance')
    commit(links,'endurance','Endurance — коміт із 30-хвилинним тестом')
    paragraph(d,'Виконав повний 30-хвилинний інтервал при 25 VU. Разом із 30-секундним розгоном і 30-секундним завершенням профіль триває 31 хвилину. Перші й останні п’ять хвилин сталого інтервалу порівняв окремо; розгін до цих значень не включений.')
    e=data['endurance'];m=sums['endurance']['metrics']
    table(d,['Період','Запити','Середній час','p95','Помилки'],[[label,count(e[key]['requests']),ms(e[key]['avg_ms']),ms(e[key]['p95_ms']),pct(e[key]['failure_rate'])] for label,key in [('Перші 5 хв','first_5min'),('Останні 5 хв','last_5min')]],[1.45,1.15,1.7,1.5,1.2])
    image(d,R/'endurance-chart.png','Рисунок 4  Метрики протягом повного тесту витривалості')
    mem=e['api_memory'];change=e['last_5min']['p95_ms']/e['first_5min']['p95_ms']-1
    paragraph(d,f'За весь тест виконано {count(m["http_reqs"]["values"]["count"])} запитів, помилок - {pct(m["http_req_failed"]["values"]["rate"])}. За останні п’ять хвилин p95 змінився на {number(change*100,1)} % порівняно з першими. При 25 VU протягом цих 30 хвилин погіршення роботи не помітив.')
    minute_values=list(e['steady_minutes'].values())
    if all(row['p95_ms']<500 and row['failure_rate']<.01 for row in minute_values):
        paragraph(d,f'За обраним SLO деградації не виявлено: p95 у кожній із 30 хвилин залишався нижчим за 500 мс. Діапазон хвилинних p95 - від {ms(min(row["p95_ms"] for row in minute_values))} до {ms(max(row["p95_ms"] for row in minute_values))}.')
    else:
        paragraph(d,'Окремі хвилинні інтервали порушили обраний SLO; часовий графік показує їхнє розташування. Підсумкові агрегати слід оцінювати разом із цими відхиленнями.')
    paragraph(d,f'Медіани приватної пам’яті API у перших та останніх п’яти хвилинах сталого навантаження - {number(mem["first_5min_median_mb"],1)} та {number(mem["last_5min_median_mb"],1)} МБ, максимум - {number(mem["peak_mb"],1)} МБ. Початкове зростання припало на розгін. Для перевірки витоків потрібні довші запуски та профілювання heap.')
    page(d,'7 Додаткові завдання та відтворення')
    heading(d,'GitHub Actions',2);commit(links,'ci','Коміт із налаштуванням CI та експорту метрик')
    paragraph(d,'Додав окремий workflow k6 performance smoke. Він запускає PostgreSQL як нативний сервіс runner-а, встановлює Node.js і k6, готує тестову БД, очікує /health, виконує smoke зі строгими порогами й зберігає HTML звіт та JSON метрики як artifact. Цей запуск є перевіркою регресій; його швидкодію не порівнюю з локальним Windows baseline.')
    links.append((ci['url'],'Успішний запуск smoke у GitHub Actions'))
    table(d,['Крок CI','Результат'],[['Нативний PostgreSQL і схема','Успішно'],['Підготовка тестових даних та запуск API','Успішно'],['k6 smoke і перевірка порогів','Успішно'],['Збереження artifact','Успішно']],[5.45,1.55])
    heading(d,'Експорт і графіки',2)
    paragraph(d,'Для кожного тесту зберіг HTML звіт k6 web dashboard і метрики у JSON. Для цього використав K6_WEB_DASHBOARD_EXPORT та --out json. За збереженими даними побудував графіки з кроком 5 секунд. Як додаткові завдання виконав запуск smoke тесту в CI та експорт метрик із графіками.')
    heading(d,'Повторний запуск',2)
    paragraph(d,'Створити окрему БД traveler_lab2, встановити DATABASE_URL, виконати npm ci --omit=dev, node scripts/init-db.js та запустити API. Далі послідовно виконати scripts/run-performance.ps1 з параметром -Test smoke, load, stress, spike або endurance. Сценарії одночасно не запускати. Команди й параметри збережені у tests/performance-tests/README.md та *-run.json.')
    heading(d,'Висновок',2)
    paragraph(d,'У роботі перевірив TravelerAPI з першої лабораторної за допомогою п’яти тестів k6. При 200 одночасних користувачах p95 залишався нижчим за 500 мс. Під час stress і spike затримки зросли, але після зменшення навантаження API відновив нормальну роботу. За 30 хвилин endurance при 25 VU помилок і поступового погіршення не виявлено. Ці результати можна порівняти з наступними реалізаціями за тих самих умов.')
    paragraph(d,'Використані методичні вказівки: SumDU.CS.DDS.Lab2v_1.pdf. Посилання на репозиторій, коміти та документацію наведені наприкінці звіту.')
    for label,url in [
        ('Початкові k6 сценарії викладача','https://github.com/potapuff/SumDU.DDS.25F.lab2'),
        ('Документація k6 web dashboard','https://grafana.com/docs/k6/latest/results-output/web-dashboard/'),
        ('Документація сценаріїв k6','https://grafana.com/docs/k6/latest/using-k6/scenarios/'),
    ]:
        links.append((url,label))
    page(d,'Додаток А. Smoke і Load: знімки результатів')
    paragraph(d,'На скріншотах показані збережені результати тестів. Тут наведені підсумки за весь запуск, а в таблицях вище — за окремі періоди сталого навантаження.')
    screenshot(d,'01-smoke',5,'Результати smoke тесту')
    screenshot(d,'02-load',6,'Результати load тесту')

    page(d,'Додаток Б. Stress і Spike: перевантаження')
    paragraph(d,'Позначка FAIL означає, що під великим навантаженням p95 перевищив 500 мс. Після зменшення навантаження час відповіді повернувся до норми.')
    screenshot(d,'03-stress',7,'Результати stress тесту')
    screenshot(d,'04-spike',8,'Результати spike тесту')

    page(d,'Додаток В. Endurance: підсумок і профіль')
    screenshot(d,'05-endurance',9,'Результати endurance тесту')
    screenshot(d,'06-endurance-start',10,'Початок endurance тесту')
    paragraph(d,'Основне навантаження тривало 30 хвилин. Разом із розгоном і завершенням тест зайняв 31 хвилину.')

    page(d,'Додаток Г. Завершення Endurance і Hurl у CI')
    screenshot(d,'07-endurance-finish',11,'Завершення endurance тесту')
    screenshot(d,'08-ci-hurl',12,'Успішні тести Hurl у GitHub Actions')

    page(d,'Додаток Д. Конкурентні тести та стан CI')
    screenshot(d,'09-ci-concurrency',13,'Успішні тести конкурентного доступу')
    heading(d,'Виправлення середовища GitHub Actions',2)
    paragraph(d,'Спочатку Hurl у CI не запускався через відсутню бібліотеку libxml2.so.2. Вибрав Ubuntu 24.04 і додав встановлення libxml2. Після цього пройшли всі 56 запитів Hurl і три тести конкурентного доступу. Код API та схему БД не змінював.')
    proof=load(R/'ci-functional-proof.json')
    links.append((BASE+'/commit/'+proof['head_sha'],'Коміт із виправленням запуску Hurl у CI'))
    table(d,['Перевірка на цьому коміті','Результат'],[[r['name']+' / '+r['event'],r['conclusion']] for r in proof['runs']],[5.45,1.55])
    links.append((BASE+'/pull/1/checks','Стан перевірок лабораторної на GitHub'))

    page(d,'Посилання')
    link_table=table(d,['Посилання','Що відкриває'],[['',label] for url,label in links],[4.75,2.25])
    for row,(url,label) in zip(link_table.rows[1:],links):
        hyperlink(row.cells[0].paragraphs[0],url,url)
        for p in row.cells[1].paragraphs:
            p.alignment=WD_ALIGN_PARAGRAPH.LEFT
    # The bundled Word template adds a blue rule to Title. Keep academic titles plain.
    for root in (d.element,d.styles.element):
        for border in list(root.xpath('.//w:pBdr')):
            border.getparent().remove(border)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);d.save(output)
    print(output)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();main(args.output)
