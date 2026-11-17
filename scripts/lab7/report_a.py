# Report sections 1-6 (executed by build_report.py in its namespace).
text('Лабораторна робота 7', 'Title')
text('Варіативна 1 «Косметична»: моніторинг TravelerAPI з Prometheus і Grafana', 'Subtitle')
text('Самонов Михайло ІН.м-62/2')
text('Мета роботи - покращити проєкт TravelerAPI в межах варіативної частини курсу. З п’яти запропонованих варіантів обрав варіант 4 - '
     'моніторинг з Prometheus і Grafana.')
text('Додав у шардований TravelerAPI з лабораторної №6 метрики Prometheus (бібліотека prom-client), підключив до кожного з чотирьох сервісів '
     'PostgreSQL окремий postgres_exporter, налаштував Prometheus зі збором метрик і правилами алертів та Grafana з двома дашбордами, які '
     'створюються з файлів. Перевірив моніторинг на чотирьох дослідах: навантаження k6, «гарячий» шард, зупинка одного сервісу PostgreSQL '
     'і перенесення шардів під навантаженням. Окремо виміряв, скільки коштує сам моніторинг.')
text('GitHub:')
link(BRANCH, 'Код лабораторної №7 (гілка lab7-monitoring)')
table(['Що зроблено', 'Де в репозиторії', 'Розділ'], [
    ['Метрики API, GET /metrics', 'src/metrics.js, src/shards.js, src/app.js', '3'],
    ['Метрики PostgreSQL', '4 × postgres_exporter, роль lab7_monitor', '4'],
    ['Prometheus і 11 правил алертів', 'monitoring/prometheus', '5'],
    ['Grafana: datasource і 2 дашборди', 'monitoring/grafana, scripts/lab7/dashboards.py', '6'],
    ['Досліди з навантаженням і відмовами', 'scripts/lab7/lab7.py, tests/performance-tests', '7-11'],
    ['Тести: Hurl для /metrics, promtool для алертів, CI', 'tests/metrics.hurl, alerts.test.yml, .github/workflows', '3, 5, 12'],
], [2.6, 3.0, 0.9])

heading('1 Вибір варіанта і початковий проєкт')
text('Викладач запропонував п’ять варіантів: GUI, кращі тести, завантаження фотографій у S3 повз сервер застосунку, моніторинг з Prometheus '
     'і Grafana, швидкий пошук з Elasticsearch. Обрав моніторинг, бо після лабораторної №6 TravelerAPI став розподіленою системою: два '
     'екземпляри API, чотири сервіси PostgreSQL і 16 баз даних-шардів. Без моніторингу не видно, як навантаження ділиться між шардами, чи '
     'всі сервіси доступні і що відбувається під час перенесення шарду. Решта варіантів менше пов’язані з розподіленим зберіганням даних '
     '(GUI, пошук) або потребують нових зовнішніх сервісів і змін у моделі даних (S3, Elasticsearch).')
text('Продовжив код з гілки lab6-sharding і створив нову гілку lab7-monitoring. REST API, схему БД, шардування, CLI shard-exec і rebalance.js '
     'з лабораторної №6 не змінював. Файл docker-compose.lab6.yml також лишився без змін: усе нове описано в окремому файлі '
     'docker-compose.monitoring.yml, який Compose об’єднує з ним.')
table(['Компонент', 'Версія і налаштування'], [
    ['Комп’ютер', 'Intel Core i5-11300H, 8 логічних процесорів, 16 ГБ RAM, Windows 11, Docker Desktop'],
    ['API', 'Node.js 22.18.0, Express 5, pg 8, prom-client 15.1.3; web і web2 по 2 CPU / 512 MiB'],
    ['PostgreSQL', '16.15 alpine; 4 сервіси × 4 БД (db_0..db_f), кожен 0,5 CPU / 256 MiB'],
    ['Експортер БД', 'postgres_exporter v0.17.1, по одному на сервіс PostgreSQL'],
    ['Моніторинг', 'Prometheus v3.5.0, Grafana 12.1.1'],
    ['Навантаження і тести', 'k6 2.3.0 (remote write у Prometheus), Hurl 8.0.0, promtool'],
], [1.6, 4.9])
text('Команди запуску:')
text('python scripts/lab7/bootstrap-env.py')
text('python scripts/lab7/lab7.py up')
text('python scripts/lab7/lab7.py seed')
text('Перший скрипт додає в локальний .env випадкові паролі ролі моніторингу та адміністратора Grafana (старі паролі лабораторної №6 '
     'не змінюються). Другий збирає образ і запускає Compose-проєкт traveler_lab7, третій завантажує той самий набір даних, що й у '
     'лабораторних №2-6: 2 000 планів і 6 000 локацій.')
shot('t01-compose-ps', 'Запущений проєкт traveler_lab7: 4 PostgreSQL, 2 API, 4 exporters, Prometheus і Grafana')
shot('t02-seed', 'Завантаження набору даних в усі 16 шардів через shard-exec з лабораторної №6')

heading('2 Архітектура моніторингу')
text('Prometheus працює за моделлю pull: кожні 5 секунд сам звертається до цілей і забирає метрики в текстовому форматі. Цілей сім: два '
     'екземпляри API, чотири postgres_exporter і сам Prometheus. Grafana не збирає даних сама, вона лише виконує запити PromQL до Prometheus. k6 під час '
     'навантажувальних тестів, навпаки, надсилає свої метрики в Prometheus (remote write), тому на одному графіку видно і кількість '
     'віртуальних користувачів, і реакцію API та БД.')
shot('architecture', 'Компоненти лабораторної №7: API з /metrics, 4 exporters, Prometheus і Grafana', 6.5)
table(['Сервіс', 'Мережі', 'Порт на хості', 'Призначення'], [
    ['web, web2', 'backend, frontend', '127.0.0.1:4567, :4568', 'REST API і GET /metrics'],
    ['pg_exporter_00..03', 'backend', '-', 'метрики свого сервісу PostgreSQL'],
    ['prometheus', 'backend, frontend', '127.0.0.1:9090', 'збір, зберігання, алерти'],
    ['grafana', 'frontend', '127.0.0.1:3000', 'дашборди (анонімний перегляд)'],
], [1.5, 1.4, 1.6, 2.0], font=10.5)
text('Мережа backend внутрішня (internal: true), як і в лабораторній №6: порти PostgreSQL і exporters на хості не публікуються. Prometheus '
     'під’єднаний до обох мереж, щоб бачити цілі і водночас бути доступним з браузера. Grafana бачить лише Prometheus. Обидва порти '
     'прив’язані до 127.0.0.1. Grafana відкривається без входу з роллю Viewer, редагування - лише під admin з паролем з .env.')
shot('c05-compose-exporters', 'docker-compose.monitoring.yml: роль моніторингу для PostgreSQL і чотири postgres_exporter')
shot('c06-compose-prometheus-grafana', 'docker-compose.monitoring.yml: сервіси Prometheus і Grafana')

heading('3 Метрики застосунку')
text('Для Node.js використав офіційну клієнтську бібліотеку prom-client. Усі метрики описані в новому модулі src/metrics.js, а в код API '
     'додано лише кілька викликів. Метрики зберігаються в пам’яті процесу, а GET /metrics віддає їх у текстовому форматі Prometheus. '
     'Кожен з двох екземплярів API має власні лічильники; Prometheus додає до них мітку api (web або web2).')
shot('c01-metrics-definitions', 'src/metrics.js: реєстр, метрики процесу Node.js, гістограми HTTP і запитів до БД')
table(['Метрика', 'Тип', 'Мітки', 'Що показує'], [
    ['http_request_duration_seconds', 'histogram', 'method, route, status', 'кількість і час HTTP-запитів'],
    ['http_requests_in_flight', 'gauge', '-', 'запити в обробці зараз'],
    ['db_query_duration_seconds', 'histogram', 'shard, server, kind, outcome', 'SQL-запити та транзакції до кожного шарду'],
    ['db_errors_total', 'counter', 'shard, server, code', 'помилки БД за SQLSTATE'],
    ['db_pool_connections', 'gauge', 'database, server, state', 'з’єднання 16 пулів: total, idle, waiting'],
    ['scatter_gather_duration_seconds', 'histogram', '-', 'запит одразу до всіх 16 шардів'],
    ['shard_mapping_version', 'gauge', '-', 'версія mapping у кожному API'],
    ['shard_server_info', 'gauge', 'shard, server, database', 'на якому сервісі зараз кожен шард'],
    ['shard_retries_total', 'counter', 'shard', 'повтори після перенесення шарду'],
    ['travel_plans_created_total', 'counter', 'shard', 'нові плани за шардами'],
    ['process_*, nodejs_*', 'різні', '-', 'CPU, пам’ять, event loop, GC'],
], [2.3, 0.9, 1.7, 1.7], font=10)
text('Важливо обмежити кількість значень міток: кожна унікальна комбінація - окремий часовий ряд у Prometheus. Тому мітка route - це шаблон '
     'маршруту Express (/api/travel-plans/:id), а не конкретна адреса з UUID. Значень мітки shard рівно 16, server - 4, коди SQLSTATE '
     'обмежені. Ідентифікатори планів і локацій ніколи не потрапляють у мітки.')
shot('c02-metrics-pool-middleware', 'Стан пулів читається під час збору; middleware бере шаблон маршруту; observe розрізняє помилку БД і бізнес-відкат')
text('Час запитів до БД вимірюється в src/shards.js - там, де лабораторна №6 вже вибирала шард і пул. Функція withShard тепер передає далі '
     'не лише пул, а й сервер шарду, тому мітка server показує фактичне розміщення, навіть якщо шард щойно перенесли. Відповіді 404 і 409 '
     'усередині транзакції рахуються як rollback, а не як помилка БД.')
shot('c03-shards-observe', 'src/shards.js: вимірювання запитів, транзакцій, scatter-gather і повторів після перенесення')
shot('c04-app-metrics', 'src/app.js: middleware метрик і маршрут GET /metrics')
text('Фрагмент відповіді /metrics API web після дослідів з перенесенням шардів (розділ 10). Видно, що запити до db_3 і db_7 спочатку '
     'йшли на старі сервіси, а потім на нові, mapping має версію 4, а кількість 42501 збігається з кількістю повторів. Повна відповідь '
     'одного API - близько 1 300 рядків.')
shot('t03-metrics', 'Відповідь GET /metrics: HTTP за шаблонами маршрутів, запити до шардів, пули, mapping')
text('Для /metrics додав новий файл тестів tests/metrics.hurl. Він створює, читає і видаляє план, а потім перевіряє, що відповідь /metrics '
     'має правильний Content-Type, містить гістограми з шаблоном маршруту, метрики шардів і пулів і не містить UUID створеного плану. '
     'Перевірки міток написані через регулярні вирази, бо prom-client не гарантує порядок міток у рядку.')
shot('c15-metrics-hurl', 'tests/metrics.hurl: перевірка формату і вмісту /metrics')
shot('t04-hurl', 'Усі сценарії Hurl лабораторних №2-6 і новий metrics.hurl проходять на traveler_lab7')

heading('4 Метрики PostgreSQL')
text('Для БД використав postgres_exporter - окремий процес, який підключається до PostgreSQL, читає системні представлення '
     '(pg_stat_database, pg_stat_activity, pg_locks, pg_replication_slots тощо) і віддає їх Prometheus. На кожен сервіс PostgreSQL - '
     'свій exporter. Оскільки pg_stat_database має мітку datname, а кожна БД - це окремий шард, з одного exporter видно навантаження на '
     'всі чотири шарди сервісу.')
text('Exporter не повинен мати доступу до даних. Тому сценарій ініціалізації сервісу створює окрему роль lab7_monitor лише з вбудованою '
     'роллю pg_monitor і лімітом у 5 з’єднань, а pg_hba.conf дозволяє їй під’єднуватися тільки до службової БД postgres.')
shot('c07-init-monitor-role', 'db/shard/500_init_node.sh: роль lab7_monitor з pg_monitor')
shot('c08-pg-hba', 'pg_hba.conf: роль моніторингу допущена лише до БД postgres')
shot('t05-security', 'Перевірка: lab7_monitor не суперкористувач, не має CONNECT до шардів, сесія exporter - тільки в БД postgres')
table(['Метрика postgres_exporter', 'Для чого використовую'], [
    ['pg_up', 'доступність сервісу (алерт PostgresDown)'],
    ['pg_stat_database_xact_commit / xact_rollback', 'транзакції за секунду в кожному шарді'],
    ['pg_stat_database_tup_inserted / updated / deleted / fetched', 'записані й прочитані рядки'],
    ['pg_stat_database_blks_hit / blks_read', 'частка читань із кешу (cache hit)'],
    ['pg_database_size_bytes', 'розмір кожної БД'],
    ['pg_stat_activity_count, pg_settings_max_connections', 'з’єднання і запас до max_connections'],
    ['pg_locks_count', 'блокування за сервісами'],
    ['pg_replication_slot_*', 'реплікація реєстру shard_registry з postgres_00'],
], [3.4, 3.1], font=10.5)

heading('5 Prometheus: збір метрик і алерти')
text('Конфігурація Prometheus невелика: дві групи цілей і файл правил. Для API мітка api береться з адреси цілі, для exporters мітка server '
     'задана явно. Інтервал збору - 5 секунд, як і інтервал перевірки правил.')
shot('c09-prometheus-yml', 'monitoring/prometheus/prometheus.yml')
shot('p-targets', 'Prometheus: усі 7 цілей у стані UP')
text('У вкладці Query можна виконати будь-який запит PromQL. Наприклад, кількість запитів до кожного шарду за секунду, підсумована з обох API:')
shot('p-query-shards', 'Prometheus: sum by (shard) (rate(db_query_duration_seconds_count[1m])) під час навантаження')
text('Правила алертів поділив на дві групи. Перша стосується API і шардів, друга - сервісів PostgreSQL. Кожне правило має поріг, '
     'тривалість for (щоб короткий сплеск не викликав тривогу) та опис українською. ShardDatabaseErrors агрегується за сервісом PostgreSQL: '
     'спершу правило давало окреме сповіщення на кожну пару «шард × код помилки», і під час відмови сервера сторінка алертів ставала '
     'нечитабельною. Помилки 42501 і 3D000 у нього не входять: це очікуваний сигнал перенесеного шарду з лабораторної №6, після якого API '
     'сам повторює запит.')
shot('c10-alerts-api', 'monitoring/prometheus/alerts.yml: правила для API і шардів')
shot('c11-alerts-postgres', 'monitoring/prometheus/alerts.yml: правила для PostgreSQL')
table(['Алерт', 'Умова', 'Рівень'], [
    ['TravelerApiDown', 'API не віддає /metrics 15 с', 'critical'],
    ['TravelerApiHighErrorRate', 'понад 1 % відповідей 5xx за хвилину', 'critical'],
    ['TravelerApiHighLatencyP95', 'p95 > 500 мс протягом 1 хв', 'warning'],
    ['ShardDatabaseErrors', 'помилки БД на сервісі, крім 42501 / 3D000', 'critical'],
    ['ShardPoolSaturated', 'запити чекають на з’єднання 30 с', 'warning'],
    ['ShardHotspot', 'один шард > 3 × середнього навантаження', 'warning'],
    ['ShardMappingVersionMismatch', 'API мають різні версії mapping 30 с', 'warning'],
    ['PostgresDown', 'pg_up = 0 протягом 10 с', 'critical'],
    ['PostgresExporterDown', 'exporter не відповідає 15 с', 'warning'],
    ['PostgresTooManyConnections', '> 80 % max_connections', 'warning'],
    ['RegistryReplicationSlotInactive', 'слот реплікації реєстру неактивний 1 хв', 'warning'],
], [2.4, 3.2, 0.9], font=10.5)
text('Щоб не перевіряти правила лише «на око», додав модульні тести алертів monitoring/prometheus/alerts.test.yml. promtool подає на вхід '
     'штучні часові ряди і перевіряє, які алерти і з якими мітками та описами мають спрацювати в заданий момент: PostgresDown через 10 с '
     'після pg_up = 0, помилки 5xx лише для web, гарячий шард 5, відсутність алерту при рівномірному навантаженні та ігнорування 42501.')
shot('t06-promtool', 'promtool: перевірка конфігурації і 5 тестів правил алертів')
text('Щоб переконатися, що тести справді ловлять помилки, у копії правил змінив для PostgresDown for: 10s на for: 1m. Тест «postgres_02 '
     'down» упав: у момент 40 с очікувався алерт, а його ще немає.')
shot('t07-promtool-broken', 'Тест правил падає, якщо поріг PostgresDown змінити з 10 с на 1 хв')
shot('p-rules', 'Prometheus: завантажені правила алертів')
