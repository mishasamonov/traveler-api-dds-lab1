# Report sections 8-10: hotspot, server failure, rebalance (executed by build_report.py in its namespace).
import re


def summary_of(tag, name):
    return json.loads((E / f'{tag}/{name}-summary.json').read_text(encoding='utf-8'))['metrics']


def firing(name):
    return sorted({a['labels']['alertname'] for a in json.loads((E / name).read_text(encoding='utf-8')) if a['state'] == 'firing'})


def freeze(name):
    return int(re.search(r'write freeze (\d+) ms', (E / name).read_text(encoding='utf-8')).group(1))


# ---------------------------------------------------------------- 8 hotspot
heading('8 Дослід 2: «гарячий» шард')
HOT = summary_of('hotspot', 'shards-hotspot')
HP = json.loads((E / 'hotspot-prometheus.json').read_text(encoding='utf-8'))
hot_q = HP['shardQueries']['5']; other_q = max(v for k, v in HP['shardQueries'].items() if k != '5')
text('Щоб перевірити алерт ShardHotspot на справжньому перекосі, сценарій shards-test.js у режимі MODE=hotspot 120 секунд читає й оновлює '
     'лише плани, id яких закінчується на 5. Усі ці запити йдуть в одну БД db_5 на postgres_01, хоча API та решта 15 шардів вільні.')
text('python scripts/lab7/lab7.py hotspot')
shot('c16-shards-test', 'tests/performance-tests/shards-test.js: режими uniform і hotspot, мітка server для кожного запиту')
shot('t-k6-hotspot', f'k6 у режимі hotspot: {num(HOT["http_reqs"]["values"]["rate"], 0)} запитів за секунду лише до db_5')
text(f'Кількість SQL-запитів за тест: db_5 - {num(hot_q, 0)}, кожен з інших шардів - лише {other_q} (це перевірки /health). k6 показує '
     f'{pct(HOT["http_req_failed"]["values"]["rate"])} «невдалих» запитів, але в Prometheus видно, що це відповіді з кодом 409 '
     f'(їх {HP["statuses"].get("409", 0)}): кілька VU одночасно оновлюють ті самі 119 планів, і спрацьовує optimistic locking з лабораторної №2. Помилок 5xx немає.')
shot('g-panel-distribution-hotspot', 'Розподіл запитів між шардами під час тесту hotspot: усе навантаження на db_5', 6.0)
text('Через 90 секунд від початку тесту алерт ShardHotspot був у стані firing. ShardPoolSaturated при цьому переходив у pending: у пулі '
     'з 5 з’єднань до db_5 час від часу з’являлися запити, що чекають, але не 30 секунд поспіль. На шкалі алертів дашборда видно обидва стани.')
shot('p-alerts-hotspot', 'Prometheus: алерт ShardHotspot під час навантаження на один шард', 6.3)
shot('g-api-hotspot', 'Дашборд API за час тесту hotspot', 6.5)
text('Для ключа шардування за останнім символом UUID такий перекіс можливий, лише якщо клієнти постійно звертаються до тих самих '
     'планів. Моніторинг дає ранній сигнал: такий шард варто перенести на окремий сервіс через rebalance.js з лабораторної №6 або збільшити '
     'для нього пул з’єднань.')

# ---------------------------------------------------------------- 9 failure
heading('9 Дослід 3: відмова одного сервісу PostgreSQL')
FAIL = summary_of('failure', 'shards-uniform')
FP = json.loads((E / 'failure-prometheus.json').read_text(encoding='utf-8'))
TL = json.loads((E / 'failure-alert-timeline.json').read_text(encoding='utf-8'))['rows']
text('Найцікавіше для розподіленої системи - часткова відмова. Під постійним навантаженням 40 VU на всі 16 шардів (MODE=uniform) на 35-й '
     f'секунді зупинив контейнер postgres_02 (шарди db_8..db_b) і запустив його знову через {FP["outageSeconds"]} с. Сценарій позначає кожен '
     'запит міткою сервісу, якому належить шард, тому k6 рахує результати окремо для кожного сервісу.')
text('python scripts/lab7/lab7.py failure')
shot('t-failure-log', 'Хід досліду: зупинка postgres_02, стан алертів кожні 5 с, повторний запуск')
sub('Які алерти спрацювали і коли')


def first(alert, state, target=None):
    rows = [r for r in TL if r['alert'] == alert and r['state'] == state and (target is None or r['target'] == target)]
    return min(r['fromSeconds'] for r in rows) if rows else None


timeline = [
    ('PostgresDown', 'postgres_02', first('PostgresDown', 'firing', 'postgres_02'), 'exporter не може під’єднатися до сервісу'),
    ('ShardDatabaseErrors', 'postgres_02', first('ShardDatabaseErrors', 'firing', 'postgres_02'), 'API отримує помилки від шардів 8..b'),
    ('TravelerApiHighErrorRate', 'web', first('TravelerApiHighErrorRate', 'firing', 'web'), 'понад 1 % відповідей 500'),
    ('TravelerApiHighErrorRate', 'web2', first('TravelerApiHighErrorRate', 'firing', 'web2'), 'те саме для другого API'),
    ('ShardPoolSaturated', 'postgres_02', first('ShardPoolSaturated', 'firing', 'postgres_02'), 'запити чекають на з’єднання до мертвого сервісу'),
    ('RegistryReplicationSlotInactive', 'postgres_00', first('RegistryReplicationSlotInactive', 'firing', 'postgres_00'),
     'копія реєстру на postgres_02 не отримує змін'),
]
table(['Алерт', 'Де', 'Firing через', 'Що означає'],
      [[a, t, f'{s} с' if s is not None else '-', m] for a, t, s, m in timeline], [2.2, 1.1, 0.9, 2.4], font=10)
text('PostgresDown спрацював через 20 секунд: 10 секунд правила for плюс інтервал збору. Алерт про реплікацію реєстру сховищ - теж корисний '
     'побічний сигнал: postgres_02 зберігає копію shard_registry, і слот реплікації на postgres_00 став неактивним.')
shot('p-alerts-failure', 'Prometheus під час недоступності postgres_02: алерти з описами і мітками', 6.0)
shot('g-api-failure-live', 'Дашборд API під час відмови: PostgreSQL онлайн 3, помилки 500 і тайм-аути пулів', 6.5)
shot('g-pg-failure-live', 'Дашборд PostgreSQL під час відмови: postgres_02 DOWN, інші сервіси працюють', 6.5)
sub('Що показали метрики')
rows = []
for s, sh in (('postgres_00', '0-3'), ('postgres_01', '4-7'), ('postgres_02', '8-b'), ('postgres_03', 'c-f')):
    v = lambda m: FAIL[f'{m}{{server:{s}}}']['values']
    rows.append([f'{s} ({sh})', num(v('http_reqs')['count'], 0), pct(v('http_req_failed')['rate']), ms(v('http_req_duration')['p(95)']),
                 ms(v('http_req_duration')['p(99)'], 0)])
table(['Сервіс (шарди)', 'Запитів', 'Помилки', 'p95', 'p99'], rows, [1.9, 1.1, 1.1, 1.1, 1.1], font=10.5)
text('За весь тест помилки отримали майже виключно запити до шардів postgres_02. Але дашборд показав ще одну річ, якої за підсумком k6 '
     f'не видно: до зупинки API обробляли близько {num(FP["rpsBefore"], 0)} запитів за секунду, а під час простою - лише '
     f'{num(FP["rpsDuring"], 0)}, з них {num(FP["errorRpsDuring"], 0)} - помилки 500. Тобто недоступна лише чверть даних, а пропускна '
     + ('здатність усієї системи впала більш ніж у 20 разів.' if FP['rpsBefore'] / FP['rpsDuring'] > 20
        else f'здатність усієї системи впала приблизно в {num(FP["rpsBefore"] / FP["rpsDuring"], 0)} разів.'))
shot('g-api-failure', 'Дашборд API за весь дослід: падіння пропускної здатності, 500, тайм-аути пулу і відновлення', 6.5)
codes = {f'{e["code"]} на {e["server"]}': e['count'] for e in FP['errorsByServerCode']}
pt = sum(e['count'] for e in FP['errorsByServerCode'] if e['code'] == 'pool_timeout' and e['server'] == 'postgres_02')
text(f'Причину видно на панелі помилок БД: майже всі помилки під час простою - pool_timeout на postgres_02 (їх {pt}). Запит до шарду мертвого '
     'сервісу не отримує швидку відмову, а чекає 5 секунд (connectionTimeoutMillis пулу), бо під’єднання до зупиненого контейнера не '
     'завершується одразу. Кожен VU k6 по черзі звертається до всіх шардів, тому кожен четвертий запит «зависає» на 5 секунд і тримає '
     'клієнта. Саме тому p99 запитів до postgres_02 дорівнює 5 секундам, а алерт TravelerApiHighErrorRate спрацював пізніше за PostgresDown.')
shot('g-panel-errors-failure', 'Помилки БД за кодом SQLSTATE під час відмови: здебільшого pool_timeout на postgres_02', 6.0)
others = [e for e in FP['errorsByServerCode'] if e['server'] != 'postgres_02']
text(f'Наприкінці простою з’явилися також поодинокі тайм-аути на здорових сервісах ({", ".join(f"{e["count"]} на {e["server"]}" for e in others)}), '
     'і ShardDatabaseErrors ненадовго спрацював і для них. Імовірна причина - пули до здорових БД закрили простоюючі з’єднання '
     '(idleTimeoutMillis 30 с), а нові під’єднання чекали в черзі на DNS-запити до postgres_02, які в Node.js виконуються в спільному пулі '
     f'потоків libuv. Після запуску postgres_02 помилки зникли приблизно через {FP["errorsStopSecond"] - FP["restartSecond"]} с, API '
     f'без перезапуску відновився до {num(FP["rpsAfter"], 0)} запитів за секунду, а алерти перейшли в resolved.')
text('Висновок досліду: шардування справді ізолює дані - три чверті планів залишались доступними. Але без «швидкої відмови» для '
     'недоступного шарду (короткий тайм-аут під’єднання або circuit breaker) часткова відмова майже зупиняє весь API. Це покращення варто '
     'зробити наступним, а для production - ще й реплікацію кожного шарду з автоматичним failover, як у лабораторній №5 (Patroni).')

# ---------------------------------------------------------------- 10 rebalance
heading('10 Дослід 4: перенесення шардів під навантаженням')
REB = summary_of('rebalance', 'rebalance')
text('У лабораторній №6 перенесення БД між сервісами (rebalance.js) я перевіряв за логами і підсумком k6. Тепер повторив той самий сценарій '
     'і подивився на нього в Grafana: 120 секунд 60 VU через обидва API, на 35-й секунді db_3 переноситься з postgres_00 на postgres_03, '
     'на 75-й - db_7 з postgres_01 на postgres_02.')
text('python scripts/lab7/lab7.py rebalance')
sub('Перша спроба: deadlock')
text('Під час першого запуску перенесення db_7 пройшло, а db_3 - ні: на кроці LOCK TABLE travel_plans, locations IN ACCESS EXCLUSIVE MODE '
     'PostgreSQL виявив взаємне блокування і перервав транзакцію інструмента. Інструмент відкотив блокування, і джерело далі обслуговувало '
     'шард, тому клієнти не отримали жодної помилки. У лабораторній №6 цей випадок просто не трапився.')
shot('t-move-first-db_3', 'Перша спроба перенесення db_3: deadlock detected на кроці 3, джерело продовжує працювати')
text('Причина в порядку блокувань. Інструмент блокує спочатку travel_plans, потім locations, а транзакції API - по-різному: додавання '
     'локації блокує план, а оновлення локації спочатку читає locations і лише потім блокує план. Будь-який фіксований порядок у '
     'rebalance.js може зіткнутися з однією з них. На кроці 3 ще нічого не змінено, тому найпростіше рішення - відкотити блокування і '
     'повторити спробу. Додав у tools/rebalance.js до п’яти спроб при помилках 40P01 (deadlock) і 55P03 (lock timeout).')
shot('t-retry-db_5', 'Перевірка повтору: сесія тримає locations 12 с, перша спроба отримує 55P03, друга успішна', 6.5)
text('Повтор перевірив детерміновано: окрема сесія psql тримала блокування таблиці locations у db_5 12 секунд, поки rebalance.js переносив '
     'db_5. Перша спроба завершилась тайм-аутом 55P03, друга дочекалась звільнення таблиці й успішно перенесла шард. Час заморожування '
     f'записів {num(freeze("rebalance-retry-db_5.txt") / 1000)} с тут включає очікування на чужу транзакцію.')
sub('Повторний дослід')
text(f'Після виправлення повторив дослід на чистих БД. Обидва перенесення пройшли з першої спроби: записи в db_3 були заморожені '
     f'{freeze("rebalance-move-db_3.txt")} мс, у db_7 - {freeze("rebalance-move-db_7.txt")} мс. Кількість запитів за 120 секунд - '
     f'{num(REB["http_reqs"]["values"]["count"], 0)}, частка помилок {pct(REB["http_req_failed"]["values"]["rate"])}.')
shot('t-move-db_3', 'rebalance.js: перенесення db_3 на postgres_03 під навантаженням')
shot('g-panel-placement-rebalance', 'Розміщення шардів: db_3 переходить на postgres_03, db_7 - на postgres_02', 6.0)
text('На шкалі «Розміщення шардів» рядки db_3 і db_7 змінюють колір на колір нового сервісу, а версія mapping в обох API зростає з 1 до 3. '
     'На панелі помилок видно кілька 42501 на старих сервісах і стільки ж повторів для шардів 3 і 7 - це очікуваний механізм лабораторної №6: '
     'запити, що чекали на блокування, після REVOKE отримують 42501, API перечитує mapping і повторює запит на новому сервісі. Алерт '
     'ShardDatabaseErrors не спрацював, бо 42501 виключено з правила.')
shot('g-panel-errors-rebalance', '42501 на старих сервісах (стовпці) і повтори запитів для db_3 та db_7 (пунктир)', 6.0)
text('Щоб ці серії були видні одразу після старту API, лічильники 42501, 3D000 і повторів створюються з нулем під час завантаження mapping. '
     'Без цього перший 42501 з’являвся як нова серія вже зі значенням, і функція increase() у Prometheus його не бачила.')
shot('g-api-rebalance', 'Дашборд API під час двох перенесень', 6.5)
shot('g-pg-rebalance', 'Дашборд PostgreSQL: транзакції db_3 і db_7 переходять на нові сервіси', 6.5)
text('На дашборді PostgreSQL транзакції db_3 зникають на postgres_00 і з’являються на postgres_03, а db_7 переходить з postgres_01 на '
     'postgres_02. Стара копія з відкликаними правами залишається на джерелі, тому на панелі розміру db_3 і db_7 видно двічі. Після всіх '
     'перенесень (mapping v4) знову запустив сценарії Hurl - усі пройшли.')
shot('t-hurl-after', 'Hurl після перенесень: усі сценарії, разом із metrics.hurl, проходять на новому розміщенні')
