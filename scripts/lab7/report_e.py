# Conclusions and links (executed by build_report.py in its namespace).
heading('13 Висновки')
text('Для варіативної лабораторної обрав моніторинг з Prometheus і Grafana і додав його до шардованого TravelerAPI з лабораторної №6, не '
     'змінюючи REST API, схему БД і файл Compose попередньої роботи. API віддає метрики через prom-client: HTTP за шаблонами маршрутів, '
     'запити до кожного з 16 шардів, стан пулів, версію mapping і розміщення шардів. Чотири postgres_exporter з окремою роллю pg_monitor '
     'показують стан кожного сервісу PostgreSQL і навантаження на кожну БД. Prometheus збирає це кожні 5 секунд і перевіряє 11 правил '
     'алертів, а Grafana будує два дашборди, які разом із джерелом даних створюються з файлів у Git.')
text(f'Досліди показали, що моніторинг корисний саме для розподіленої системи. Під час Load він виявив два шарди db_{HOTS[0]} і db_{HOTS[1]}, '
     'які отримували більше запитів через однаковий created_at у тестових даних; за підсумком k6 цього не було видно. Алерт ShardHotspot '
     'спрацював на штучному гарячому шарді, а під час зупинки postgres_02 алерти одразу вказали на сервіс і шарди, тоді як три чверті даних '
     'залишались доступними. Перенесення шардів з лабораторної №6 стало видно на графіках: зміна сервера, версії mapping, 42501 і повтори '
     'без жодної помилки для клієнта.')
text(f'Моніторинг має свою ціну: на найпростішому запиті пропускна здатність API зменшилась приблизно на {num(loss * 100, 0)} %. Крім того, '
     'мітки потрібно обмежувати, щоб не створювати зайві часові ряди. Також додав тести самого моніторингу: Hurl для /metrics, модульні тести '
     'алертів у promtool і workflow GitHub Actions, який перевіряє конфігурацію Prometheus, дашборди і Compose-файл.')

heading('Посилання')
link(BRANCH, 'Код лабораторної №7')
for key, label in (('code', 'Метрики, Prometheus, Grafana, тести моніторингу'), ('evidence', 'Досліди, скріншоти та звіт')):
    if key in COMMITS: link(f'{BASE}/commit/{COMMITS[key]}', label)
link('https://prometheus.io/docs/practices/naming/', 'Prometheus: назви метрик і міток')
link('https://grafana.com/docs/grafana/latest/administration/provisioning/', 'Grafana: provisioning')
link('https://github.com/prometheus-community/postgres_exporter', 'postgres_exporter')
text('На скріншотах терміналу показані збережені результати команд і фрагменти коду з репозиторію; знімки Grafana і Prometheus зроблені '
     'в браузері. Оригінальні файли - в evidence/lab7.')
