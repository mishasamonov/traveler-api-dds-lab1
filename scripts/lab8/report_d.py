# Report sections 9-12: indexes and plans, size and WAL, rebalancing, contract (executed by build_report.py in its namespace).
import re as _re
WAL = json.loads((E / 'wal.json').read_text(encoding='utf-8'))


def exec_ms(name):
    return [float(x) for x in _re.findall(r'Execution Time: ([\d.]+) ms', (E / f'{name}.txt').read_text(encoding='utf-8'))]


def mb_of(label):
    m = _re.search(label + r'\s*\|[^\n]*\|\s*([\d.]+) MB\s*$', (E / 'bench-sizes.txt').read_text(encoding='utf-8'), _re.M)
    return float(m.group(1))


# ---------------------------------------------------------------- 9
heading('9 Індекси JSONB і плани запитів')
text('На шардах лише по 100-140 планів, тому PostgreSQL часто обирає послідовне читання і різниці в планах не видно. Для EXPLAIN створив '
     'окрему БД jsonb_bench на postgres_00: 50 000 планів по 3 локації (як у наборі лабораторної №2) і ще три плани з 20, 100 і 300 '
     'локаціями. Дані спочатку завантажуються в реляційні таблиці, а потім переносяться тими самими скриптами 002 + 100, що й на шардах, '
     'тож у цій БД є обидві версії даних: legacy_* і plan_documents. Кожен запит виконувався двічі в одній сесії, на рисунках - другий запуск.')
text('python scripts/lab8/lab8.py explain')
shot('t-bench-sizes', 'jsonb_bench: завантаження, міграція і розмір таблиць до і після')
get_rel = exec_ms('explain-get-relational'); get_doc = exec_ms('explain-get-jsonb')
text(f'Читання плану з локаціями: у реляційній моделі це два пошуки за індексом (план за PK, локації за індексом (travel_plan_id, '
     f'visit_order)), разом {num(sum(get_rel), 3)} мс виконання плюс два звернення API до БД. У JSONB - один Index Scan за PK, '
     f'{num(get_doc[0], 3)} мс.')
shot('t-explain-get-relational', 'EXPLAIN ANALYZE: план і його локації в реляційній моделі - два запити')
shot('t-explain-get-jsonb', 'EXPLAIN ANALYZE: документ плану за первинним ключем - один запит')
gin = exec_ms('explain-location-gin'); seq = exec_ms('explain-location-seqscan'); rel = exec_ms('explain-location-relational')
text(f'Пошук документа за id локації - запит PUT і DELETE /api/locations/:id. З GIN-індексом jsonb_path_ops це Bitmap Index Scan, '
     f'{num(gin[0], 3)} мс. Щоб побачити, навіщо індекс, вимкнув для сесії індексні плани: тоді PostgreSQL перебирає всі 50 тисяч документів '
     f'і перевіряє @> у кожному - {num(seq[0], 1)} мс, приблизно в {num(seq[0] / gin[0], 0)} разів довше. У реляційній моделі той самий пошук - '
     f'просто первинний ключ locations ({num(rel[0], 3)} мс). Документна модель тут нічого не виграє, але завдяки GIN і не програє.')
shot('t-explain-location-gin', 'Пошук документа за id локації: GIN jsonb_path_ops')
shot('t-explain-location-seqscan', 'Той самий запит без індексу: послідовний перебір документів')
shot('t-explain-location-relational', 'Реляційна модель: локація за первинним ключем')
lr = exec_ms('explain-list-relational'); lj = exec_ms('explain-list-jsonb')
text(f'Друга фаза списку для 20 планів: у реляційній моделі - з’єднання з locations і групування для підрахунку локацій ({num(lr[0], 3)} мс), '
     f'у JSONB - читання 20 документів і довжина масиву ({num(lj[0], 3)} мс).')
shot('t-explain-list-relational', 'Друга фаза списку в реляційній моделі: JOIN і GROUP BY')
shot('t-explain-list-jsonb', 'Друга фаза списку в JSONB: jsonb_array_length без JOIN')

# ---------------------------------------------------------------- 10
heading('10 Ціна документів: розмір і обсяг WAL')
rel_mb = mb_of('legacy_locations') + mb_of('legacy_travel_plans'); doc_mb = mb_of('plan_documents')
text(f'Розмір. У jsonb_bench документи разом з індексами займають {num(doc_mb, 0)} МБ, а ті самі дані в двох реляційних таблицях - '
     f'{num(rel_mb, 0)} МБ, тобто в {num(doc_mb / rel_mb, 1)} раза більше. Середній документ плану з 3 локаціями - 1 466 байт, а рядок плану '
     'і три рядки локацій разом - близько 670 байт. У кожному документі зберігаються назви всіх полів, а числа і дати - у вигляді JSON, а не '
     'компактних date, numeric і timestamptz. Стиснення TOAST вмикається лише для значень понад ~2 КБ, тож звичайний документ не стискається.')
text('Посилення запису. Коли змінюється одна локація, PostgreSQL записує нову версію всього документа. Виміряв це через EXPLAIN (ANALYZE, WAL): '
     'той самий UPDATE однієї локації (поле notes і версія) в реляційній таблиці і в документі, для планів з 3, 20, 100 і 300 локаціями. '
     'Кожен запит виконувався чотири рази в одній сесії в транзакції, яку потім відкочував; враховано останній запуск, коли кеш теплий, '
     'функція CHECK уже скомпільована, а повних копій сторінок після контрольної точки вже немає.')
rows = []
for r in WAL:
    a, b = r['relational'], r['jsonb']
    rows.append([str(r['locations']), num(r['doc_bytes'], 0), f"{a['records']} / {num(a['bytes'], 0)}", f"{b['records']} / {num(b['bytes'], 0)}",
                 num(b['bytes'] / a['bytes'], 1) + '×', f"{num(a['ms'], 2)} / {num(b['ms'], 2)}"])
table(['Локацій у плані', 'Документ, Б', 'WAL реляц.: записів / Б', 'WAL JSONB: записів / Б', 'JSONB / реляц.', 'Час, мс: реляц. / JSONB'],
      rows, [0.9, 0.95, 1.3, 1.3, 0.85, 1.3], font=10)
shot('t-wal', 'WAL і час виконання UPDATE однієї локації залежно від розміру документа')
shot('t-wal-explain-relational', 'EXPLAIN (ANALYZE, WAL): реляційний UPDATE - HOT-оновлення одного рядка')
shot('t-wal-explain-jsonb', 'EXPLAIN (ANALYZE, WAL): UPDATE документа зі 100 локаціями')
w3, w100, w300 = WAL[0], WAL[2], WAL[3]
text(f'Реляційне оновлення не залежить від кількості локацій: завжди {w3["relational"]["records"]} записи WAL, '
     f'{num(w3["relational"]["bytes"], 0)} байт. Поля notes і version не входять в індекси, тому PostgreSQL робить HOT-оновлення без нових '
     f'записів в індексах. Оновлення документа пропорційне його розміру: для плану з 3 локаціями - {num(w3["jsonb"]["bytes"], 0)} байт '
     f'({num(w3["jsonb"]["bytes"] / w3["relational"]["bytes"], 1)}×) і {num(w3["jsonb"]["ms"], 2)} мс, а для 300 локацій - уже '
     f'{num(w300["jsonb"]["bytes"] / 1024, 1)} КБ ({num(w300["jsonb"]["bytes"] / w300["relational"]["bytes"], 0)}×) і '
     f'{num(w300["jsonb"]["ms"], 0)} мс. Документ стає великим і йде в TOAST, а GIN-індекс на doc->\'locations\' не дає зробити HOT-оновлення, '
     'тож нові записи додаються ще й у первинний ключ, B-tree і GIN. До того ж CHECK перевіряє всі локації документа при кожній зміні.')
text('Висновок для моделі даних: документ підходить, поки агрегат обмежений. План подорожі з кількома-десятком локацій - добрий випадок. '
     'Якби в плані могли бути сотні й тисячі елементів, які часто змінюються (журнал подій, коментарі), їх варто було б залишити в окремій '
     'таблиці, а в документі зберігати лише те, що читається і змінюється разом.')

# ---------------------------------------------------------------- 11
heading('11 Перенесення шардів з JSONB')
def freeze(name): return int(_re.search(r'write freeze (\d+) ms', (E / name).read_text(encoding='utf-8')).group(1))
def step_ms(name, n): return int(_re.search(rf'^{n}\. [^|]*\| (\d+)', (E / name).read_text(encoding='utf-8'), _re.M).group(1))
RB = json.loads((E / 'rebalance/rebalance-summary.json').read_text(encoding='utf-8'))['metrics']
RF = json.loads((E / 'rebalance-failed/rebalance-summary.json').read_text(encoding='utf-8'))['metrics']
text('Перевірив, що інструмент перенесення шардів з лабораторної №6 працює з новою схемою. rebalance.js тепер сам визначає схему БД, '
     'яку переносить: для JSONB він створює на цільовому сервісі схему з 002_plan_documents.sql, реплікує і блокує лише plan_documents '
     '(і маленьку storage_migrations), а крок з видаленням і відновленням відкладеного UNIQUE більше не потрібен.')
shot('c15-rebalance-layouts', 'tools/rebalance.js: дві схеми зберігання')
text('Повторив дослід лабораторної №7: 120 секунд 60 VU через обидва API, на 35-й секунді db_3 переноситься з postgres_00 на postgres_03, '
     'на 75-й - db_7 з postgres_01 на postgres_02.')
text('python scripts/lab8/lab8.py rebalance')
sub('Перша спроба: початкове копіювання не завершується')
text(f'Перша спроба не вдалася: обидва перенесення зупинились на кроці 2 - таблиці так і не перейшли в стан «готово», і через 150 секунд '
     f'інструмент перервав роботу. Клієнти цього не помітили: джерело продовжувало обслуговувати шарди, k6 виконав '
     f'{num(RF["http_reqs"]["values"]["count"], 0)} запитів без жодної помилки. У журналі цільового PostgreSQL знайшлися дві причини.')
shot('t-rebalance-failed-log', 'Помилки воркера логічної реплікації на цільовому сервісі')
text('Перша - права. storage_migrations створена вже після створення БД, і роль реплікації не має на неї SELECT. Друга - цікавіша. Воркер '
     'початкового копіювання вставляє рядки з порожнім search_path (так PostgreSQL захищає логічну реплікацію від підміни функцій), а CHECK '
     'при вставці викликає plan_document_valid, яка всередині звертається до location_document_valid без назви схеми. З порожнім '
     'search_path така функція не знаходиться. Так само зламалось би відновлення з pg_dump, яке теж працює з порожнім search_path.')
text('Виправлення: у rebalance.js перед створенням публікації явно видаю ролі реплікації SELECT на таблиці, які публікуються, а у 002 виклик '
     'став public.location_document_valid. Щоб ця помилка не повторилась, міграція 120 тепер перевіряє всі документи з порожнім search_path. '
     'Без виправлення вона падає на всіх 16 шардах і все відкочується, з виправленою схемою - проходить.')
shot('t-search-path-before-fix', 'Перевірка з порожнім search_path до виправлення: помилка на всіх 16 шардах, ROLLBACK')
shot('t-search-path-fix-shard-exec', 'Виправлена схема 002 + перевірка 120 з порожнім search_path: COMMIT на всіх 16 шардах')
sub('Повторна спроба')
f3, f7 = freeze('rebalance-move-db_3.txt'), freeze('rebalance-move-db_7.txt')
text(f'Після прибирання залишків першої спроби (підписки, слоти реплікації, недокопійовані БД) повторив дослід. Обидва перенесення пройшли '
     f'з першої спроби, k6 виконав {num(RB["http_reqs"]["values"]["count"], 0)} запитів, частка помилок '
     f'{pct(RB["http_req_failed"]["values"]["rate"])}. Записи в db_3 були заморожені {f3} мс, у db_7 - {f7} мс.')
shot('t-rebalance-move-db_3', 'Перенесення db_3 (JSONB) на postgres_03 під навантаженням')
text(f'Це довше, ніж у лабораторній №7 з двома таблицями (366 і 296 мс). З таблиці кроків видно чому: під блокуванням (крок 3) інструмент '
     f'чекає, поки підписник застосує останні зміни, і рахує md5 усіх даних з обох боків. Для документів це {step_ms("rebalance-move-db_3.txt", 3)} '
     f'і {step_ms("rebalance-move-db_7.txt", 3)} мс проти 78 і 45 мс у лабораторній №7: оновлення документа пише в кілька разів більше WAL, а md5 '
     'рахується по документах JSONB. Решту вікна займає крок 5 - оновлення реєстру і очікування трьох його копій, який від схеми даних '
     'не залежить і під навантаженням коливається. Зате блокується одна таблиця даних, і проблема з порядком блокувань двох таблиць, через '
     'яку в лабораторній №7 виникав deadlock, зникла сама собою.')
shot('t-k6-rebalance', 'k6 під час двох перенесень шардів: жодної помилки')
shot('g-api-rebalance', 'Дашборд API під час перенесення db_3 і db_7', 6.5)
shot('t-hurl-final', 'Після перенесень: усі тести проходять на новому розміщенні шардів (mapping v3)')

# ---------------------------------------------------------------- 12
heading('12 Завершення міграції')
SB = json.loads((E / 'sizes-before-contract.json').read_text(encoding='utf-8'))
SA = json.loads((E / 'sizes-after-contract.json').read_text(encoding='utf-8'))
SV = json.loads((E / 'sizes-after-vacuum.json').read_text(encoding='utf-8'))
mb = lambda v: num(v / 1048576, 1) + ' МБ'
text('Коли нова версія пройшла всі перевірки і тести навантаження, виконав останній крок - видалив резервні реляційні таблиці на всіх '
     '16 шардах тим самим shard-exec. Після цього повернутися назад усе ще можна, але лише через 190_rollback_to_relational.sql, тобто '
     'з документів.')
text('python scripts/lab8/lab8.py contract     # node tools/shard-exec.js /sql/110_drop_legacy.sql')
shot('t-contract-shard-exec', 'Видалення legacy-таблиць на 16 шардах')
text(f'Тут же видно ще один бік посилення запису. Після всіх тестів plan_documents на 16 шардах займала {mb(sum(r["jsonb"] for r in SB))}, '
     f'хоча живих даних там значно менше: кожне оновлення залишало стару версію документа, а autovacuum лише позначає це місце як вільне '
     f'для повторного використання. Після VACUUM FULL таблиця зменшилась до {mb(sum(r["jsonb"] for r in SV))}. Для документної моделі під '
     'інтенсивним записом варто стежити за роздуванням таблиці (у лабораторній №7 для цього вже є панель розміру БД у Grafana).')
