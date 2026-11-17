# Report sections: overhead, GitHub, conclusions, links (executed by build_report.py in its namespace).
import statistics
OV = json.loads((E / 'overhead.json').read_text(encoding='utf-8'))
med = {m: {k: statistics.median(r[k] for r in OV[m]) for k in ('rps', 'p95', 'avg')} for m in ('on', 'off')}
loss = 1 - med['on']['rps'] / med['off']['rps']

heading('11 Скільки коштує моніторинг')
text('Метрики рахуються в тому самому процесі, що й обробка запитів, тому моніторинг не безкоштовний. Щоб оцінити це, додав змінну METRICS: '
     'при METRICS=off middleware і observe нічого не роблять, а /metrics повертає 404. Контрольний тест key-test.js з лабораторної №6 '
     '(200 VU, 45 с, лише GET /api/travel-plans/:id, тобто запити до одного шарду) запускав по черзі з метриками і без них, '
     'по три рази. Без метрик Prometheus також зупинявся.')
text('python scripts/lab7/lab7.py overhead')
table(['Режим', 'Запуски, запитів за с', 'Запитів за с (медіана)', 'p95 (медіана)', 'Помилки'], [
    ['METRICS=on, Prometheus працює', ', '.join(num(r['rps']) for r in OV['on']), num(med['on']['rps']), ms(med['on']['p95']),
     pct(max(r['failed'] for r in OV['on']))],
    ['METRICS=off, Prometheus зупинений', ', '.join(num(r['rps']) for r in OV['off']), num(med['off']['rps']), ms(med['off']['p95']),
     pct(max(r['failed'] for r in OV['off']))],
], [2.0, 1.9, 1.0, 0.9, 0.7], font=10.5)
text(f'На найпростішому запиті моніторинг забирає близько {num(loss * 100, 0)} % пропускної здатності API: на кожен HTTP-запит '
     'виконуються два вимірювання гістограм (HTTP і SQL) з кількома мітками, а prom-client кожні 5 секунд серіалізує понад тисячу '
     'рядків для Prometheus. Різниця в p95 менша за розкид між запусками. Для системи, де API можна масштабувати горизонтально, це прийнятна '
     'ціна за видимість, але її варто знати. Зменшити її можна меншою кількістю кошиків гістограм, рідшим збором або вибірковим '
     'вимірюванням SQL.')

heading('12 Код у GitHub')
text('Код, конфігурацію моніторингу, сценарії дослідів, збережені результати та скріншоти завантажив у гілку lab7-monitoring того самого '
     'репозиторію, що й попередні лабораторні.')
shot('gh-branch', 'Гілка lab7-monitoring на GitHub', 6.0)
shot('gh-commits', 'Коміти лабораторної №7', 6.0)
shot('gh-monitoring', 'Каталог monitoring: конфігурація Prometheus і Grafana в репозиторії', 6.0)
text('У GitHub Actions працюють два workflow. Старий «TravelerAPI tests» запускає API з 16 шардами в одному PostgreSQL і проганяє всі '
     'сценарії Hurl, тепер разом із tests/metrics.hurl. Новий «Monitoring configuration» перевіряє prometheus.yml і правила через promtool, '
     'запускає тести алертів, перевіряє, що JSON дашбордів відповідає scripts/lab7/dashboards.py, і що Compose-файл моніторингу коректний.')
shot('gh-actions', 'Успішні запуски обох workflow для гілки lab7-monitoring', 6.0)
shot('gh-actions-monitoring', 'Кроки workflow Monitoring configuration', 6.0)
