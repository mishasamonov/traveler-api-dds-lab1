# Report sections 8-10: hotspot, server failure, rebalance (executed by build_report.py in its namespace).
def k6_tagged(tag):
    return json.loads((E / f'{tag}/shards-{"hotspot" if tag == "hotspot" else "uniform"}-summary.json').read_text(encoding='utf-8'))['metrics']


def alert_names(name):
    return sorted({a['labels']['alertname'] for a in json.loads((E / name).read_text(encoding='utf-8')) if a['state'] == 'firing'})


heading('8 Дослід 2: «гарячий» шард')
HOT = k6_tagged('hotspot')
hot_alerts = alert_names('hotspot-alerts-firing.json')
text('Щоб перевірити алерт ShardHotspot на справжньому перекосі, сценарій shards-test.js у режимі MODE=hotspot 120 секунд читає й оновлює '
     'лише плани, id яких закінчується на 5. Усі ці запити йдуть в одну БД db_5 на postgres_01, хоча API і решта шардів вільні.')
text('python scripts/lab7/lab7.py hotspot')
shot('c16-shards-test', 'tests/performance-tests/shards-test.js: режими uniform і hotspot, мітка server для кожного запиту')
shot('t-k6-hotspot', f'k6 у режимі hotspot: {num(HOT["http_reqs"]["values"]["rate"])} запитів за секунду лише до db_5')
text('Через 90 секунд від початку тесту в Prometheus горіли алерти: ' + ', '.join(hot_alerts) + '. Перший - саме про нерівномірність: '
     'запитів до db_5 у десятки разів більше, ніж у середньому на шард. ShardPoolSaturated показує наслідок: пул з 5 з’єднань до db_5 у '
     'кожному API не встигає, і запити чекають у черзі, хоча пули решти 15 БД простоюють.')
shot('p-alerts-hotspot', 'Prometheus: алерти під час навантаження на один шард', 6.3)
shot('g-api-hotspot-live', 'Дашборд API під час тесту hotspot: стовпчик db_5 і черга пулу на postgres_01', 6.5)
text('Для шардування з ключем за останнім символом UUID такий перекіс можливий, лише якщо клієнти постійно звертаються до тих самих '
     'планів. Моніторинг дає ранній сигнал: такий шард варто перенести на окремий сервіс через rebalance.js з лабораторної №6 або збільшити '
     'його пул з’єднань.')

heading('9 Дослід 3: відмова одного сервісу PostgreSQL')
FAIL = k6_tagged('failure')
fail_events = json.loads((E / 'failure-events.json').read_text(encoding='utf-8'))
stop_ev = next(e for e in fail_events['events'] if 'stop' in e); start_ev = next(e for e in fail_events['events'] if 'start' in e and 'ms' in e)
outage = (start_ev['ms'] - stop_ev['ms']) / 1000
fail_alerts = alert_names('failure-alerts-firing.json')


def tag_rate(metric, server):
    v = FAIL.get(f'{metric}{{server:{server}}}')
    return v['values']['rate'] if v else 0


text('Найцікавіше для розподіленої системи - часткова відмова. Під постійним навантаженням 40 VU на всі 16 шардів (MODE=uniform) на 35-й '
     f'секунді зупинив контейнер postgres_02 (шарди db_8..db_b) і запустив його знову через {num(outage, 0)} с. Сценарій позначає кожен '
     'запит міткою сервісу, якому належить шард, тому k6 рахує помилки окремо для кожного сервісу.')
text('python scripts/lab7/lab7.py failure')
shot('t-failure-log', 'Хід досліду: зупинка postgres_02, алерти кожні 5 с, повторний запуск')
text('Через 10-15 секунд після зупинки спрацювали алерти: ' + ', '.join(fail_alerts) + '. Prometheus показує, на якому сервісі і в '
     'яких шардах проблема, а не лише загальне «API повертає 500».')
shot('p-alerts-failure', 'Prometheus: алерти під час недоступності postgres_02', 6.3)
shot('g-api-failure-live', 'Дашборд API під час відмови: PostgreSQL онлайн 3, помилки лише для шардів 8..b', 6.5)
shot('g-pg-failure-live', 'Дашборд PostgreSQL під час відмови: postgres_02 DOWN, інші сервіси працюють', 6.5)
table(['Сервіс (шарди)', 'Запитів', 'Помилки', 'p95'], [
    [f'{s} ({sh})', num(FAIL[f'http_reqs{{server:{s}}}']['values']['count'], 0) if f'http_reqs{{server:{s}}}' in FAIL else '-',
     pct(tag_rate('http_req_failed', s)),
     ms(FAIL[f'http_req_duration{{server:{s}}}']['values']['p(95)']) if f'http_req_duration{{server:{s}}}' in FAIL else '-']
    for s, sh in (('postgres_00', '0-3'), ('postgres_01', '4-7'), ('postgres_02', '8-b'), ('postgres_03', 'c-f'))
], [2.0, 1.4, 1.4, 1.4], font=10.5)
text('Помилки отримали лише запити до шардів postgres_02, решта три чверті даних залишалися доступними весь час: так виглядає '
     'перевага шардування для доступності. Без моніторингу цю ситуацію легко сплутати з повною відмовою API.')
shot('g-api-failure', 'Дашборд API за весь дослід: помилки 5xx і SQLSTATE під час простою, відновлення після запуску postgres_02', 6.5)
text('Після запуску postgres_02 з тим самим томом даних API без перезапуску відновив роботу: пули створили нові з’єднання, помилки '
     'зникли, і алерти перейшли в стан resolved. Для production тут потрібна реплікація кожного шарду з автоматичним failover, як у '
     'лабораторній №5 (Patroni), а моніторинг дає сигнал, що вона спрацювала або ні.')

heading('10 Дослід 4: перенесення шардів під навантаженням')
REB = json.loads((E / 'rebalance/rebalance-summary.json').read_text(encoding='utf-8'))['metrics']
reb_events = json.loads((E / 'rebalance-events.json').read_text(encoding='utf-8'))
text('У лабораторній №6 перенесення БД між сервісами (rebalance.js) я перевіряв за логами і k6. Тепер повторив той самий сценарій і подивився '
     'на нього в Grafana: 120 секунд 60 VU через обидва API, на 35-й секунді db_3 переноситься з postgres_00 на postgres_03, на 75-й - db_7 '
     'з postgres_01 на postgres_02.')
text('python scripts/lab7/lab7.py rebalance')
shot('t-move-db_3', 'rebalance.js: перенесення db_3 на postgres_03 під навантаженням')
shot('g-api-rebalance', 'Дашборд API під час двох перенесень', 6.5)
text(f'На дашборді видно всі етапи перенесення. На шкалі «Розміщення шардів» рядки db_3 і db_7 змінюють колір на колір нового сервісу. '
     'Версія mapping в обох API зростає з 1 до 3. На панелі помилок з’являються короткі сплески 42501 на старих сервісах і стільки ж '
     'повторів для шардів 3 і 7 - це очікуваний механізм лабораторної №6: після REVOKE API перечитує mapping і повторює запит. Алерт '
     'ShardDatabaseErrors при цьому не спрацював, бо 42501 виключено з правила, а помилок 5xx не було: '
     f'{pct(REB["http_req_failed"]["values"]["rate"])} з {num(REB["http_reqs"]["values"]["count"], 0)} запитів.')
shot('g-panel-placement-rebalance', 'Розміщення шардів: db_3 переходить на postgres_03, db_7 - на postgres_02', 6.0)
shot('g-panel-errors-rebalance', 'Помилки 42501 на старих сервісах і повтори запитів після перенесення', 6.0)
shot('g-pg-rebalance', 'Дашборд PostgreSQL: транзакції db_3 і db_7 переходять на нові сервіси', 6.5)
text('На дашборді PostgreSQL транзакції db_3 зникають на postgres_00 і з’являються на postgres_03, а db_7 - переходить з postgres_01 на '
     'postgres_02. Стара копія з відкликаними правами залишається на джерелі, тому на панелі розміру БД db_3 і db_7 видно двічі.')
shot('t-hurl-after', 'Hurl після перенесень: усі сценарії, разом із metrics.hurl, проходять на новому розміщенні')
