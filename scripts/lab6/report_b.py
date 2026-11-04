# Section 6: performance before and after sharding.
import collections
NAMES = {'baseline': '1 БД (№4), 1 API', 'baseline-2api': '1 БД (№4), 2 API', 'sharded-naive': '16 БД 4×0,5 CPU, 1 API, перша версія',
         'sharded-equal': '16 БД 4×0,5 CPU, 1 API', 'sharded-scaled': '16 БД 4×2 CPU, 1 API', 'sharded-scaled-2api': '16 БД 4×2 CPU, 2 API'}


def cpu(tag):
    rows = [json.loads(l) for l in (E / f'{tag}-docker-stats.jsonl').read_text(encoding='utf-8').splitlines() if l]
    agg = collections.defaultdict(list)
    for r in rows: agg[r['Name']].append(float(r['CPUPerc'].rstrip('%')))
    out = {}
    for k, v in agg.items():
        name = k.split('-')[1] if k.count('-') >= 2 else k
        out[name] = sum(v) / len(v)
    return out


L = {k: A[k]['load'] for k in NAMES}
P = {k: A[k]['plateaus'] for k in NAMES}
R = {k: A[k]['read'] for k in NAMES}
naive_cpu, equal_cpu, base_cpu = cpu('sharded-naive-load'), cpu('sharded-equal-load'), cpu('baseline-load')
pg_naive = sum(v for k, v in naive_cpu.items() if k.startswith('postgres_')) / 4


def change(a, b): return num((a / b - 1) * 100, 1) + ' %'


heading('6 Вимірювання продуктивності')
text('Для основного порівняння використав незмінений Load з лабораторної №2: 170 секунд, розгін до 25, 50, 100 і 200 VU, кожне плато по 30 секунд. '
     'Ітерація містить вісім читань (список планів і деталі свого плану), два оновлення з version і п’ять пауз по 100 мс; кожна десята також '
     'створює й видаляє тимчасовий план із локацією. Критерії: p95 < 500 мс, http_req_failed < 1 %, checks > 99 %. Окремо тричі запускав Read: '
     '200 VU без пауз 45 секунд чергують список планів і деталі плану. Перед кожним запуском дані відновлювалися до 2 000 планів і 6 000 локацій.')
text('Порівнював такі конфігурації. Базова - незмінений образ лабораторної №4 з однією БД 2 CPU / 1 GiB і пулом 20 з’єднань. Перша шардована має '
     '4 × 0,5 CPU / 256 MiB, тобто ті самі сумарні ресурси БД, що й базова. Друга шардована має 4 × 2 CPU / 1 GiB: кожен сервіс отримує стільки, скільки '
     'одна БД у базовій, як при горизонтальному масштабуванні на чотири сервери. Спочатку навантаження йшло на один API з лімітом 2 CPU. '
     'Для перевірки масштабування API додав nginx (round-robin, 1 CPU) перед двома екземплярами API і повторив ті самі тести як для шардованої, '
     'так і для базової схеми (у базовій - два контейнери незміненого образу №4 з однією БД).')
sub('6.1 Перший вимір і вузьке місце')
nl = L['sharded-naive']
text(f'Перша версія списку планів брала з кожної з 16 БД перші page × limit повних рядків разом з COUNT локацій, а API об’єднував їх. Load з '
     f'4 × 0,5 CPU показав p95 {ms(nl["p95"])} і {num(nl["rps"])} запитів за секунду проти p95 {ms(L["baseline"]["p95"])} і '
     f'{num(L["baseline"]["rps"])} у базовій конфігурації. За docker stats процес API використовував у середньому {num(naive_cpu["web"], 0)} % CPU, '
     f'а кожен сервіс PostgreSQL - лише {num(pg_naive, 0)} % (з доступних 50 %). Отже, у вузьке місце уперся API, а не БД.')
shot('t21-sharded-naive-load', 'Перший Load на 16 БД: API перевантажений об’єднанням списку')
text('Причина в об’єднанні даних. Для сторінки 10 по 20 планів кожна БД повертала до 200 повних рядків з довгим описом, тобто API на один запит '
     'розбирав до 3 200 рядків, щоб віддати 20. У базовій конфігурації БД сама сортує і віддає лише 20. Тому розділив запит на два етапи (розділ 3.3): '
     'з 16 БД беруться тільки id і ключ сортування, а повні рядки й COUNT - лише для 20 id вибраної сторінки з їхніх шардів. Решту коду не змінював '
     'і повторив ті самі запуски.')
sub('6.2 Результати')
table(['Конфігурація', 'Середній час', 'p95', 'Запитів за с', 'Помилки'],
      [[NAMES[k], ms(L[k]['avg']), ms(L[k]['p95']), num(L[k]['rps']), pct(L[k]['failed'])] for k in NAMES], [2.6, 1.1, 1.1, 1.1, 0.9], font=10.5)
text('Метрики в таблиці - для всього запуску Load, включно з розгоном. Код завершення k6 99 означає лише порушення порога p95 < 500 мс; '
     'неочікуваних HTTP помилок немає в жодному запуску.')
table(['Конфігурація', '25 VU', '50 VU', '100 VU', '200 VU'],
      [[NAMES[k], *[ms(P[k][str(v)]['p95'], 0) for v in (25, 50, 100, 200)]] for k in NAMES], [2.6, 1.0, 1.0, 1.0, 1.0], font=10.5)
text('Друга таблиця - p95 на сталих частинах плато (по 5 секунд відкинуто з кожного краю), обчислений із сирого JSON k6.')
fig('load-plateaus', 'p95 і пропускна здатність на сталих плато Load', 6.5)
for k in ('baseline', 'sharded-equal', 'sharded-scaled', 'sharded-scaled-2api'):
    shot(f't21-{k}-load', f'Підсумок Load: {NAMES[k]}')
table(['Конфігурація', 'Read, запитів за с (медіана)', 'p95 (медіана)', 'Запуски, запитів за с'],
      [[NAMES[k], num(R[k]['median_rps']), ms(R[k]['median_p95']), ' / '.join(num(r['rps'], 0) for r in R[k]['runs'])] for k in NAMES],
      [2.4, 1.6, 1.2, 1.6], font=10.5)
fig('read-comparison', 'Read: 200 VU без пауз, медіана трьох запусків', 6.3)
