# Report section 8: before / after under load, the CHECK bottleneck and its fix (executed by build_report.py in its namespace).
AFTER1 = json.loads((E / 'bench-after-v1.json').read_text(encoding='utf-8'))
CC_SQL = json.loads((E / 'check-cost-sql.json').read_text(encoding='utf-8'))
CC_PL = json.loads((E / 'check-cost-plpgsql.json').read_text(encoding='utf-8'))
avg = lambda xs: sum(xs) / len(xs)


def change(b, a): return (a / b - 1) * 100


def sgn(v): return ('+' if v >= 0 else '−') + num(abs(v), 1) + ' %'


L_b, L_1, L_a = BEFORE['load'], AFTER1['load'], AFTER['load']
K_b, K_1, K_a = BEFORE['key'], AFTER1['key'], AFTER['key']
C_b, C_1, C_a = BEFORE['locations'], AFTER1['locations'], AFTER['locations']
NAMES = {'load': 'Load', 'key': 'Key', 'locations': 'Locations'}

heading('8 Продуктивність до і після міграції')
text('Порівняв обидві версії на тому самому стенді і тих самих даних трьома тестами k6 на API web. Load - незмінений сценарій лабораторної '
     '№2 (170 с, від 25 до 200 VU; список, читання, оновлення плану і локації, створення і видалення плану). Key - контрольний тест '
     'лабораторної №6 (200 VU, 45 с, лише GET плану за id). Locations - новий сценарій для операцій з локаціями, де SQL змінився найбільше: '
     '50 VU протягом 60 с читають свій план, змінюють першу локацію, додають нову і видаляють її.')
text('python scripts/lab8/lab8.py bench --tag before    # traveler-api:lab7, реляційні таблиці')
text('python scripts/lab8/lab8.py bench --tag after     # traveler-api:lab8, plan_documents')
shot('c17-locations-test', 'tests/performance-tests/locations-test.js: операції з локаціями')
text('Перед кожним тестом скрипт обнуляє pg_stat_statements на всіх чотирьох сервісах, а після тесту збирає статистику запитів ролі API '
     'до шардів db_0..db_f. Так видно точну кількість SQL-запитів (разом з BEGIN і COMMIT), їхній середній час і обсяг WAL.')

sub('Перший вимір: читання швидше, запис повільніше')
text(f'Перший прогін після міграції дав неоднозначний результат. Читання плану за id стало швидшим: {num(K_b["rps"], 0)} → {num(K_1["rps"], 0)} '
     f'запитів за секунду, один SQL-запит замість двох. Load майже не змінився. А тест Locations, де багато записів, став повільнішим: '
     f'{num(C_b["rps"], 0)} → {num(C_1["rps"], 0)} запитів за секунду, хоча SQL-запитів на HTTP-запит стало вдвічі менше '
     f'({num(C_b["sql_per_request"], 2)} → {num(C_1["sql_per_request"], 2)}).')
shot('t-pgss-locations-before', 'pg_stat_statements за тест Locations до міграції: багато дешевих запитів')
shot('t-pgss-locations-after-v1', 'pg_stat_statements за тест Locations після міграції (перша версія): мало запитів, але UPDATE документа дорогий')
text('pg_stat_statements показав причину: до міграції кожен запит виконувався за десяті частки мілісекунди, а після - кожен UPDATE документа '
     'займав у середньому кілька мілісекунд. На ненавантаженій БД заміряв один такий UPDATE з CHECK і без нього (обмеження прибирав '
     'усередині транзакції, яку потім відкочував):')
shot('t-check-cost-sql', 'Скільки коштує CHECK у першій версії: функції мовою SQL')
text(f'Майже весь час оновлення забирала перевірка документа: {num(avg(CC_SQL["with_check"]), 2)} мс з CHECK проти '
     f'{num(avg(CC_SQL["without_check"]), 2)} мс без нього. Причина в тому, як PostgreSQL виконує функції мовою SQL. Просту SQL-функцію '
     'він вбудовує у вираз, але plan_document_valid містить підзапити (NOT EXISTS і count(DISTINCT) над jsonb_array_elements), тому вбудувати її '
     'не можна, і тіло функції заново розбирається і планується для кожного UPDATE. На сервісі з 0,5 CPU під навантаженням ця мілісекунда '
     'процесорного часу і перетворювалась на кілька мілісекунд очікування.')
shot('c22-check-v1', 'Перша версія plan_document_valid: SQL-функція з підзапитами')

sub('Виправлення: PL/pgSQL і зміна схеми без зупинки')
text('Переписав обидві функції на PL/pgSQL (їх остаточний вигляд - на рисунках розділу 3). PL/pgSQL зберігає плани своїх запитів на весь час '
     'сесії, а пул з’єднань API тримає сесії відкритими. Унікальність порядку і id тепер перевіряється в циклі через множину вже бачених '
     'значень (оператор ? для ключів JSONB), а не двома count(DISTINCT).')
text('Схема змінюється міграцією 120 через той самий shard-exec: 002_plan_documents.sql ідемпотентний, тому повторне виконання замінює функції, '
     'а 120 перевіряє новою функцією всі збережені документи (CHECK не перевіряє старі рядки, коли змінюється його функція). '
     'API при цьому продовжував працювати: CREATE OR REPLACE FUNCTION не блокує таблицю.')
shot('c21-sql-120', 'sql/120_plpgsql_document_check.sql: перевірка всіх документів новою функцією')
shot('t-plpgsql-shard-exec', 'Заміна функцій перевірки на 16 шардах')
shot('t-check-cost-plpgsql', 'Скільки коштує CHECK на PL/pgSQL')
text(f'Перевірка тепер займає {num(avg(CC_PL["with_check"]) - avg(CC_PL["without_check"]), 2)} мс замість '
     f'{num(avg(CC_SQL["with_check"]) - avg(CC_SQL["without_check"]), 2)} мс, тобто приблизно в '
     f'{num((avg(CC_SQL["with_check"]) - avg(CC_SQL["without_check"])) / (avg(CC_PL["with_check"]) - avg(CC_PL["without_check"])), 0)} '
     'разів менше. Після цього повторив усі три тести.')

sub('Підсумок')
rows = []
for k in ('load', 'key', 'locations'):
    b, a1, a = BEFORE[k], AFTER1[k], AFTER[k]
    rows.append([NAMES[k], num(b['rps'], 0), num(a1['rps'], 0), num(a['rps'], 0), ms(b['p95'], 0), ms(a['p95'], 0),
                 f"{num(b['sql_per_request'], 2)} → {num(a['sql_per_request'], 2)}"])
table(['Тест', 'Запитів/с до', 'JSONB, SQL-CHECK', 'JSONB, PL/pgSQL', 'p95 до', 'p95 після', 'SQL на HTTP-запит'],
      rows, [0.95, 0.95, 1.0, 1.0, 0.95, 0.95, 1.1], font=10)
text(f'Помилок не було в жодному тесті. Остаточно пропускна здатність змінилась так: читання плану за id {sgn(change(K_b["rps"], K_a["rps"]))} '
     f'(p95 {ms(K_b["p95"], 0)} → {ms(K_a["p95"], 0)}), тест Locations {sgn(change(C_b["rps"], C_a["rps"]))}, Load '
     f'{sgn(change(L_b["rps"], L_a["rps"]))}. Зміни в Locations і Load у межах розкиду між запусками. У Load різниця найменша:більшу частину часу там займає список, а його перша фаза - '
     '16 паралельних запитів до всіх шардів - однакова в обох версіях. Поріг p95 < 500 мс у Load на ступені 200 VU не виконується в жодній '
     'версії, як і в лабораторних №6-7: обмеження тут - чотири сервіси PostgreSQL по 0,5 CPU і scatter-gather списку.')
shot('t-k6-key-before', 'k6 Key до міграції (реляційні таблиці)')
shot('t-k6-key-after', 'k6 Key після міграції (JSONB)')
shot('t-k6-locations-before', 'k6 Locations до міграції')
shot('t-k6-locations-after', 'k6 Locations після міграції і виправлення CHECK')
ops = []
for op in ('GET plan', 'PUT location', 'POST location', 'DELETE location'):
    ob, o1, oa = C_b['ops'][op], C_1['ops'][op], C_a['ops'][op]
    ops.append([op, ms(ob['avg']), ms(o1['avg']), ms(oa['avg']), ms(ob['p95']), ms(oa['p95'])])
text('Час окремих операцій у тесті Locations (avg - середній):')
table(['Операція', 'avg до', 'avg, SQL-CHECK', 'avg, PL/pgSQL', 'p95 до', 'p95 після'], ops, [1.5, 1.0, 1.1, 1.1, 1.0, 1.0], font=10)
shot('t-pgss-locations-after', 'pg_stat_statements за тест Locations після виправлення')
text(f'Ціну документів видно в стовпці WAL: оновлення документа записує в журнал весь документ, а не один рядок локації. У тесті Locations '
     f'на один HTTP-запит припадало {num(C_b["wal_per_request"], 0)} байт WAL до міграції і {num(C_a["wal_per_request"], 0)} байт після, '
     f'у Load - {num(L_b["wal_per_request"], 0)} і {num(L_a["wal_per_request"], 0)} байт. Детально це виміряв у розділі 10.')
sub('Load: підсумок k6 і дашборди Grafana')
shot('t-k6-load-before', 'k6 Load до міграції')
shot('t-k6-load-after', 'k6 Load після міграції')
shot('g-api-load-before', 'Дашборд API за тест Load до міграції', 6.5)
shot('g-api-load-after', 'Дашборд API за тест Load після міграції', 6.5)
shot('g-pg-all-bench', 'Дашборд PostgreSQL за всі прогони: до міграції, перша версія JSONB і версія з PL/pgSQL', 6.5)
text('На дашборді PostgreSQL видно, що після міграції транзакцій за секунду на тих самих тестах стало менше: кожен окремий запит поза явною '
     'транзакцією PostgreSQL рахує як транзакцію, тому графік повторює зменшення кількості SQL-запитів з таблиці вище.')
