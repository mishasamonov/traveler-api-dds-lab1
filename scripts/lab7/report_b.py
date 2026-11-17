# Report section 6 (Grafana) and 7 (load) - executed by build_report.py in its namespace.
load = json.loads((E / 'load/load-summary.json').read_text(encoding='utf-8'))['metrics']
load_rps = load['http_reqs']['values']['rate']; load_p95 = load['http_req_duration']['values']['p(95)']
load_n = load['http_reqs']['values']['count']; load_failed = load['http_req_failed']['values']['rate']
SHARD = json.loads((E / 'load-shard-queries.json').read_text(encoding='utf-8'))
q = {r['shard']: r['queries'] for r in SHARD['rows']}
CREATED = json.loads((E / 'created-at.json').read_text(encoding='utf-8'))
HOTS = [r['shard'] for r in CREATED[-2:]][::-1]           # the two shards loaded last (newest created_at)
newest = sum(r['plans'] for r in CREATED[-2:])
others = [v for k, v in q.items() if k not in HOTS]
TOP = sorted(q, key=q.get, reverse=True)[:2]

heading('6 Grafana: дашборди з файлів')
text('Grafana налаштовується без ручних дій в інтерфейсі (provisioning): під час старту контейнер читає опис джерела даних і постачальника '
     'дашбордів з monitoring/grafana/provisioning, а самі дашборди - JSON-файли з monitoring/grafana/dashboards. Після docker compose up '
     'усе вже готове, а будь-яка зміна дашборда проходить через Git.')
shot('c12-grafana-datasource', 'Джерело даних Prometheus (uid prometheus, лише читання)')
shot('c13-grafana-provider', 'Постачальник дашбордів з каталогу /etc/grafana/dashboards')
text('JSON дашборда Grafana довгий і незручний для ручного редагування, тому генерую його скриптом scripts/lab7/dashboards.py: у ньому для '
     'кожної панелі записані лише назва, запит PromQL, одиниці та розмір. Workflow у GitHub Actions перевіряє, що закомічені JSON-файли '
     'збігаються з результатом скрипта.')
shot('c14-dashboards-shards', 'scripts/lab7/dashboards.py: панелі розділу «Шарди: 16 віртуальних вузлів»')
text('Дашборд «TravelerAPI — API і шарди» має 25 панелей у чотирьох розділах: огляд (запити за секунду, p95, частка 5xx, кількість '
     'доступних API та PostgreSQL, версія mapping і шкала алертів), HTTP, шарди та процеси Node.js. Дашборд «PostgreSQL — 4 сервіси, '
     '16 шардів» показує стан сервісів, транзакції за БД і за сервісами, змінені й прочитані рядки, розмір кожної БД, з’єднання, '
     'блокування і реплікацію реєстру сховищ.')
shot('g-home', 'Grafana: папка TravelerAPI з двома дашбордами', 6.0)

heading('7 Дослід 1: навантаження Load з лабораторної №2')
text('Запустив незмінений сценарій Load з лабораторної №2 на API web: 170 секунд, ступені 25, 50, 100 і 200 віртуальних користувачів (VU). '
     'k6 надсилав свої метрики в Prometheus, тому в Grafana видно і навантаження, і реакцію системи.')
text('python scripts/lab7/lab7.py load')
shot('t-k6-load', 'Підсумок k6 Load: ' + num(load_rps) + ' запитів за секунду, p95 ' + ms(load_p95) + ', 0 помилок')
shot('g-api-load', 'Дашборд API за час тесту Load', 6.5)
text(f'Значення в Grafana збігаються з k6. За {num(load_n, 0)} запитів k6 нарахував {num(load_rps)} запитів за секунду і p95 {ms(load_p95)}; '
     f'панель огляду для того самого проміжку показує близькі значення (p95 у Prometheus обчислюється з гістограми, тому точність - до меж '
     f'кошиків 0,5 / 0,75 / 1 / 1,5 / 2 с). Помилок немає: {pct(load_failed)}. Алерт TravelerApiHighLatencyP95 спрацював на ступені '
     '200 VU, де p95 перевищив поріг 500 мс, - так само, як поріг k6 з лабораторної №2.')
shot('g-pg-load', 'Дашборд PostgreSQL за час тесту Load', 6.5)
sub('Що показав моніторинг: два «гарячі» шарди')
hot_servers = sorted({r['server'] for r in CREATED[-2:]})
text(f'На панелі «Розподіл запитів між шардами» видно, що db_{HOTS[0]} і db_{HOTS[1]} отримали {num(q[HOTS[0]] / 1000)} і '
     f'{num(q[HOTS[1]] / 1000)} тис. запитів, а кожен з інших 14 шардів - від {num(min(others) / 1000)} до {num(max(others) / 1000)} тис. '
     f'Через це пули до {" і ".join(hot_servers)} мали черги з’єднань, а p95 запитів туди був помітно вищим, ніж до інших сервісів. '
     'Те саме я побачив і в першому, пробному запуску Load, тільки тоді «гарячими» були інші два шарди.')
shot('g-panel-distribution-load', f'Запити до кожного шарду за тест Load: db_{HOTS[0]} і db_{HOTS[1]} помітно вище', 6.0)
shot('g-panel-pools-load', 'Пули з’єднань і p95 запитів до БД за сервісами під час Load', 6.0)
text('Причина виявилась у наборі даних, а не в шардуванні. shard-exec завантажує кожен шард в окремій транзакції, тому всі плани одного '
     f'шарду мають однаковий created_at - час цієї транзакції. db_{HOTS[1]} і db_{HOTS[0]} завантажились останніми, і їхні {newest} планів '
     'стали найновішими. '
     'Load запитує сторінки 1-10 списку по 20 планів, тобто якраз 200 найновіших, і друга фаза scatter-gather для кожної сторінки йде '
     'лише в db_e і db_f. Перевірив це запитом до БД:')
shot('t-created-at', 'Однаковий created_at усередині шарду; db_e і db_f мають найпізніший час')
text('У реальних даних плани створюються в різний час, і такого перекосу не буде. Але приклад добре показує користь моніторингу: за '
     'середніми цифрами k6 цього не видно, а розбивка за шардами одразу показує нерівномірність. Алерт ShardHotspot при цьому не спрацював: '
     'перекіс близько 1,4 разу, а поріг - утричі вище середнього. Справжній гарячий шард перевірив окремо в розділі 9.')
