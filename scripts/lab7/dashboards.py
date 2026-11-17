"""Laboratory 7: generate the Grafana dashboards (JSON) from PromQL definitions.
python scripts/lab7/dashboards.py  ->  monitoring/grafana/dashboards/*.json"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'monitoring/grafana/dashboards'
DS = {'type': 'prometheus', 'uid': 'prometheus'}
R = '[$__rate_interval]'
API = 'route!~"/health|/metrics"'
SHARD_DB = 'datname=~"db_.*"'
SERVER_COLORS = {'postgres_00': 'blue', 'postgres_01': 'green', 'postgres_02': 'orange', 'postgres_03': 'purple'}


class Board:
    def __init__(self, uid, title, description):
        self.uid, self.title, self.description = uid, title, description
        self.panels, self.id = [], 0
        self.x = self.y = self.h = 0  # left-to-right placement on a 24-column grid

    def add(self, panel, w, h):
        if self.x + w > 24: self.x, self.y, self.h = 0, self.y + self.h, 0
        self.id += 1
        panel.update(id=self.id, gridPos={'x': self.x, 'y': self.y, 'w': w, 'h': h})
        self.x, self.h = self.x + w, max(self.h, h)
        self.panels.append(panel)

    def row(self, title):
        if self.x: self.y += self.h
        self.id += 1
        self.panels.append({'type': 'row', 'id': self.id, 'title': title, 'collapsed': False, 'panels': [],
                            'gridPos': {'x': 0, 'y': self.y, 'w': 24, 'h': 1}})
        self.x, self.y, self.h = 0, self.y + 1, 0

    def json(self):
        return {'uid': self.uid, 'title': self.title, 'description': self.description, 'tags': ['traveler-api', 'lab7'],
                'timezone': 'browser', 'editable': False, 'graphTooltip': 1, 'schemaVersion': 41, 'version': 1,
                'refresh': '5s', 'time': {'from': 'now-15m', 'to': 'now'},
                'timepicker': {'refresh_intervals': ['5s', '10s', '30s', '1m']},
                'links': [{'title': 'TravelerAPI', 'type': 'dashboards', 'tags': ['traveler-api'], 'asDropdown': False}],
                'annotations': {'list': [{'builtIn': 1, 'datasource': {'type': 'grafana', 'uid': '-- Grafana --'}, 'enable': True,
                                          'hide': True, 'iconColor': 'rgba(0, 211, 255, 1)', 'name': 'Annotations & Alerts',
                                          'type': 'dashboard'}]},
                'templating': {'list': []}, 'panels': self.panels}


def t(expr, legend='', ref='A', instant=False):
    q = {'datasource': DS, 'expr': expr, 'legendFormat': legend or '__auto', 'refId': ref}
    q.update({'instant': True, 'range': False} if instant else {'range': True})
    return q


def targets(*items):  # items: expr or (expr, legend[, ref, instant])
    out = []
    for i, item in enumerate(items):
        item = item if isinstance(item, tuple) else (item,)
        out.append(t(item[0], item[1] if len(item) > 1 else '', chr(65 + i), item[3] if len(item) > 3 else False))
    return out


def thresholds(*steps):  # steps: (value, color) with the first value None
    return {'mode': 'absolute', 'steps': [{'value': v, 'color': c} for v, c in steps]}


def timeseries(title, items, unit='short', desc='', stack=False, bars=False, overrides=(), decimals=None, min_=0,
               legend='list', calcs=(), points=False):
    custom = {'drawStyle': 'bars' if bars else 'line', 'lineWidth': 2, 'fillOpacity': 25 if stack or bars else 8,
              'showPoints': 'always' if points else 'never', 'pointSize': 6, 'spanNulls': False,
              'stacking': {'mode': 'normal' if stack else 'none', 'group': 'A'}, 'axisSoftMin': min_,
              'gradientMode': 'opacity'}
    defaults = {'unit': unit, 'custom': custom, 'color': {'mode': 'palette-classic'}}
    if decimals is not None: defaults['decimals'] = decimals
    return {'type': 'timeseries', 'title': title, 'description': desc, 'datasource': DS, 'targets': targets(*items),
            'fieldConfig': {'defaults': defaults, 'overrides': list(overrides)},
            'options': {'legend': {'displayMode': legend, 'placement': 'bottom', 'showLegend': True, 'calcs': list(calcs)},
                        'tooltip': {'mode': 'multi', 'sort': 'desc'}}}


def stat(title, items, unit='short', desc='', steps=((None, 'green'),), decimals=None, mappings=(), color='background',
         text_mode='value_and_name', orientation='auto', graph='area'):
    defaults = {'unit': unit, 'thresholds': thresholds(*steps), 'color': {'mode': 'thresholds'}, 'mappings': list(mappings)}
    if decimals is not None: defaults['decimals'] = decimals
    return {'type': 'stat', 'title': title, 'description': desc, 'datasource': DS, 'targets': targets(*items),
            'fieldConfig': {'defaults': defaults, 'overrides': []},
            'options': {'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False}, 'colorMode': color,
                        'graphMode': graph, 'justifyMode': 'center', 'textMode': text_mode, 'orientation': orientation,
                        'wideLayout': True, 'showPercentChange': False}}


def bargauge(title, items, unit='short', desc='', orientation='vertical', steps=((None, 'blue'),), decimals=None):
    defaults = {'unit': unit, 'thresholds': thresholds(*steps), 'color': {'mode': 'thresholds'}, 'min': 0}
    if decimals is not None: defaults['decimals'] = decimals
    return {'type': 'bargauge', 'title': title, 'description': desc, 'datasource': DS, 'targets': targets(*items),
            'fieldConfig': {'defaults': defaults, 'overrides': []},
            'options': {'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
                        'orientation': orientation, 'displayMode': 'gradient', 'valueMode': 'text', 'namePlacement': 'auto',
                        'showUnfilled': True, 'sizing': 'auto', 'minVizHeight': 10, 'minVizWidth': 8, 'maxVizHeight': 300,
                        'text': {'titleSize': 12, 'valueSize': 14}}}


def color(name, value):
    return {'matcher': {'id': 'byName', 'options': name}, 'properties': [{'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': value}}]}


def color_regex(regex, value):
    return {'matcher': {'id': 'byRegexp', 'options': regex}, 'properties': [{'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': value}}]}


def server_overrides(prefix='.*'):
    return [color_regex(f'{prefix}{s}.*', c) for s, c in SERVER_COLORS.items()]


def q(metric, by, extra=''):
    return f'sum by ({by}) (rate({metric}{{{extra}}}{R}))'


# --------------------------------------------------------------------------- API
api = Board('traveler-api', 'TravelerAPI — API і шарди',
            'Лабораторна №7: метрики двох екземплярів API (prom-client) і запитів до 16 шардів PostgreSQL.')
api.row('Огляд')
# Overview numbers are computed over the selected time range (instant queries with $__range).
RANGE = '[$__range]'
api.add(stat('Запитів за секунду', [(f'sum(increase(http_request_duration_seconds_count{{{API}}}{RANGE})) / $__range_s', 'API', 'A', True)],
             'reqps', 'Середнє за обраний період: усі запити REST API через web і web2, крім /health і /metrics.', decimals=1,
             text_mode='value', graph='none'), 4, 4)
api.add(stat('p95 затримки API', [(f'histogram_quantile(0.95, sum by (le) (increase(http_request_duration_seconds_bucket{{{API}}}{RANGE})))', 'p95', 'A', True)],
             's', '95-й перцентиль за обраний період; поріг k6 з лабораторної №2 - 500 мс.',
             ((None, 'green'), (0.25, 'yellow'), (0.5, 'red')), decimals=2, text_mode='value', graph='none'), 4, 4)
api.add(stat('Помилки 5xx', [(f'(sum(increase(http_request_duration_seconds_count{{status=~"5..",{API}}}{RANGE})) or vector(0)) / '
                              f'clamp_min(sum(increase(http_request_duration_seconds_count{{{API}}}{RANGE})), 1e-9)', '5xx', 'A', True)],
             'percentunit', 'Частка відповідей із кодом 5xx за обраний період.', ((None, 'green'), (0.001, 'yellow'), (0.01, 'red')),
             decimals=2, text_mode='value', graph='none'), 4, 4)
api.add(stat('API онлайн', [('sum(up{job="traveler-api"})', 'API')], 'none', 'Скільки з двох екземплярів API відповідають Prometheus.',
             ((None, 'red'), (1, 'orange'), (2, 'green')), text_mode='value'), 4, 4)
api.add(stat('PostgreSQL онлайн', [('sum(pg_up)', 'PostgreSQL')], 'none', 'Скільки з чотирьох сервісів PostgreSQL доступні.',
             ((None, 'red'), (3, 'orange'), (4, 'green')), text_mode='value'), 4, 4)
api.add(stat('Версія mapping', [('max by (api) (shard_mapping_version)', '{{api}}')], 'none',
             'Версія розміщення шардів у кожному екземплярі API; зростає після кожного перенесення БД.',
             ((None, 'blue'),), color='value'), 4, 4)

alerts = 'max by (alertname) (ALERTS{alertstate="firing"}) * 2 or max by (alertname) (ALERTS{alertstate="pending"})'
api.add({'type': 'state-timeline', 'title': 'Алерти Prometheus (pending / firing)',
         'description': 'Синтетичний ряд ALERTS з Prometheus: правила з monitoring/prometheus/alerts.yml.',
         'datasource': DS, 'targets': targets((alerts, '{{alertname}}')),
         'fieldConfig': {'defaults': {'color': {'mode': 'fixed', 'fixedColor': 'gray'}, 'thresholds': thresholds((None, 'gray')),
                                      'custom': {'fillOpacity': 85, 'lineWidth': 0},
                                      'mappings': [{'type': 'value', 'options': {'1': {'text': 'pending', 'color': 'orange'},
                                                                                 '2': {'text': 'firing', 'color': 'red'}}}]},
                         'overrides': []},
         'options': {'showValue': 'auto', 'mergeValues': True, 'alignValue': 'left', 'rowHeight': 0.8,
                     'legend': {'showLegend': False}, 'tooltip': {'mode': 'single'}}}, 24, 6)

api.row('HTTP')
api.add(timeseries('Запити за секунду за маршрутами',
                   [(f'sum by (method, route) (rate(http_request_duration_seconds_count{{{API}}}{R}))', '{{method}} {{route}}')],
                   'reqps', 'Мітка route - шаблон Express (/api/travel-plans/:id), а не конкретна адреса.', stack=True), 12, 8)
api.add(timeseries('Затримка API: p50 / p95 / p99', [
    (f'histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket{{{API}}}{R})))', 'p50'),
    (f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{API}}}{R})))', 'p95'),
    (f'histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{{{API}}}{R})))', 'p99')],
    's', 'Перцентилі з гістограми http_request_duration_seconds.',
    overrides=[color('p50', 'green'), color('p95', 'orange'), color('p99', 'red')]), 12, 8)
api.add(timeseries('Відповіді за HTTP-статусом', [(f'sum by (status) (rate(http_request_duration_seconds_count{{{API}}}{R}))', '{{status}}')],
                   'reqps', '200/201/204 - успіх, 404/409 - очікувані відповіді API, 5xx - помилки.', stack=True,
                   overrides=[color_regex('2..', 'green'), color_regex('4..', 'yellow'), color_regex('5..', 'red')]), 12, 8)
api.add(timeseries('Навантаження k6 і запити в обробці', [
    ('sum by (testid) (k6_vus)', 'k6 VU: {{testid}}'),
    ('sum by (api) (http_requests_in_flight)', 'в обробці: {{api}}')],
    'short', 'k6 надсилає свої метрики в Prometheus (remote write); http_requests_in_flight - з API.',
    overrides=[color_regex('k6 VU.*', 'purple')]), 12, 8)

api.row('Шарди: 16 віртуальних вузлів')
api.add(timeseries('Запити до БД за шардами', [(q('db_query_duration_seconds_count', 'shard'), 'db_{{shard}}')], 'ops',
                   'SQL-запити й транзакції API до кожної з 16 БД (db_0..db_f).', stack=True), 12, 9)
api.add(bargauge('Розподіл запитів між шардами за обраний період',
                 [('sort_by_label(sum by (shard) (increase(db_query_duration_seconds_count[$__range])), "shard")', 'db_{{shard}}', 'A', True)],
                 'short', 'Ключ шарду - останній символ UUID плану, тому навантаження розподіляється рівномірно.', decimals=0), 12, 9)
placement = 'sort_by_label(' + ' or '.join(f'max by (shard) (shard_server_info{{server="{s}"}}) * {i}' for i, s in enumerate(SERVER_COLORS)) + ', "shard")'
api.add({'type': 'state-timeline', 'title': 'Розміщення шардів на сервісах PostgreSQL',
         'description': 'Сервер кожного шарду за даними mapping в API. Після rebalance.js колір рядка змінюється.',
         'datasource': DS, 'targets': targets((placement, 'db_{{shard}}')),
         'fieldConfig': {'defaults': {'color': {'mode': 'fixed', 'fixedColor': 'gray'}, 'thresholds': thresholds((None, 'gray')),
                                      'custom': {'fillOpacity': 85, 'lineWidth': 0},
                                      'mappings': [{'type': 'value', 'options': {str(i): {'text': s, 'color': c}
                                                                                   for i, (s, c) in enumerate(SERVER_COLORS.items())}}]},
                         'overrides': []},
         'options': {'showValue': 'auto', 'mergeValues': True, 'alignValue': 'center', 'rowHeight': 0.85,
                     'legend': {'showLegend': True, 'displayMode': 'list', 'placement': 'bottom'}, 'tooltip': {'mode': 'single'}}},
        12, 12)
api.add(timeseries('p95 запиту до БД за сервісами PostgreSQL',
                   [(f'histogram_quantile(0.95, sum by (le, server) (rate(db_query_duration_seconds_bucket{{kind="query"}}{R})))', '{{server}}')],
                   's', 'Час одного SQL-запиту з боку API (з урахуванням очікування з’єднання в пулі).',
                   overrides=server_overrides()), 12, 12)
api.add(timeseries('Пули з’єднань API: зайняті й очікують', [
    ('sum by (server) (db_pool_connections{state="total"}) - sum by (server) (db_pool_connections{state="idle"})', 'зайняті: {{server}}'),
    ('sum by (server) (db_pool_connections{state="waiting"})', 'чекають: {{server}}')],
    'short', '16 пулів pg.Pool на кожен API, по 5 з’єднань (PG_POOL_PER_SHARD).', overrides=server_overrides('.*: ')), 12, 8)
retry_style = {'matcher': {'id': 'byRegexp', 'options': 'повтор.*'},
               'properties': [{'id': 'custom.drawStyle', 'value': 'line'}, {'id': 'custom.lineWidth', 'value': 3},
                              {'id': 'custom.lineStyle', 'value': {'fill': 'dash', 'dash': [8, 4]}},
                              {'id': 'custom.fillOpacity', 'value': 0}]}
api.add(timeseries('Помилки БД (SQLSTATE) і повтори після перенесення', [
    ('sum by (code, server) (increase(db_errors_total[1m])) > 0', '{{code}} на {{server}}'),
    ('sum by (shard) (increase(shard_retries_total[1m])) > 0', 'повтор db_{{shard}}')],
    'short', 'За останню хвилину. 42501 після REVOKE старої БД - сигнал перечитати mapping; повтор іде на новий сервер.',
    bars=True, overrides=[retry_style]), 12, 8)

api.row('Процеси Node.js')
api.add(timeseries('CPU процесів API', [('sum by (api) (rate(process_cpu_seconds_total{job="traveler-api"}' + R + '))', '{{api}}')],
                   'percentunit', '1 = 100 % одного ядра, ліміт контейнера API - 2 CPU.'), 6, 8)
api.add(timeseries('Затримка event loop p99', [('max by (api) (nodejs_eventloop_lag_p99_seconds)', '{{api}}')], 's'), 6, 8)
api.add(timeseries('Пам’ять heap', [('sum by (api) (nodejs_heap_size_used_bytes)', '{{api}}')], 'bytes'), 6, 8)
api.add(timeseries('Scatter-gather 16 шардів: p95',
                   [(f'histogram_quantile(0.95, sum by (le) (rate(scatter_gather_duration_seconds_bucket{R})))', 'p95')], 's',
                   'Один запит одразу до всіх 16 БД (список планів, /health).'), 6, 8)

# ---------------------------------------------------------------------- PostgreSQL
pg = Board('traveler-postgres', 'PostgreSQL — 4 сервіси, 16 шардів',
           'Лабораторна №7: postgres_exporter на кожному з чотирьох сервісів PostgreSQL.')
pg.row('Огляд')
pg.add(stat('Стан сервісів PostgreSQL', [('max by (server) (pg_up)', '{{server}}')], 'none', 'pg_up з postgres_exporter.',
            ((None, 'red'), (1, 'green')),
            mappings=[{'type': 'value', 'options': {'0': {'text': 'DOWN', 'color': 'red'}, '1': {'text': 'UP', 'color': 'green'}}}]), 8, 4)
pg.add(stat('TPS (16 БД)', [(f'sum(increase(pg_stat_database_xact_commit{{{SHARD_DB}}}[$__range])) / $__range_s', 'TPS', 'A', True)], 'ops',
            'COMMIT за секунду в усіх БД шардів, середнє за обраний період.', ((None, 'blue'),), decimals=0, text_mode='value',
            graph='none'), 4, 4)
pg.add(stat('Розмір 16 БД', [(f'sum(pg_database_size_bytes{{{SHARD_DB}}})', 'size')], 'bytes', '', ((None, 'blue'),), decimals=1,
            text_mode='value'), 4, 4)
pg.add(stat('Активні з’єднання', [('sum(pg_stat_activity_count{state="active"})', 'active')], 'none', '', ((None, 'blue'),),
            text_mode='value'), 4, 4)
pg.add(stat('Cache hit', [(f'sum(rate(pg_stat_database_blks_hit{{{SHARD_DB}}}{R})) / clamp_min(sum(rate(pg_stat_database_blks_hit{{{SHARD_DB}}}{R})) + '
                           f'sum(rate(pg_stat_database_blks_read{{{SHARD_DB}}}{R})), 1e-9)', 'hit')], 'percentunit',
            'Частка блоків, прочитаних зі shared_buffers.', ((None, 'red'), (0.9, 'yellow'), (0.99, 'green')), decimals=1,
            text_mode='value'), 4, 4)

pg.row('Навантаження на шарди')
pg.add(timeseries('Транзакції за секунду за БД', [(q('pg_stat_database_xact_commit', 'datname, server', SHARD_DB), '{{datname}} @ {{server}}')],
                  'ops', 'pg_stat_database кожного сервісу: одна лінія на одну БД (шард).'), 12, 9)
pg.add(timeseries('Транзакції за секунду за сервісами', [(q('pg_stat_database_xact_commit', 'server', SHARD_DB), '{{server}}')],
                  'ops', 'На кожному сервісі 4 БД із 16.', stack=True, overrides=server_overrides()), 12, 9)
writes = ' + '.join(f'sum by (server) (rate(pg_stat_database_tup_{k}{{{SHARD_DB}}}{R}))' for k in ('inserted', 'updated', 'deleted'))
pg.add(timeseries('Змінені рядки за секунду (insert + update + delete)', [(writes, '{{server}}')], 'rowsps', '', stack=True,
                  overrides=server_overrides()), 12, 8)
pg.add(timeseries('Прочитані рядки за секунду (tup_fetched)', [(q('pg_stat_database_tup_fetched', 'server', SHARD_DB), '{{server}}')],
                  'rowsps', '', stack=True, overrides=server_overrides()), 12, 8)

pg.row('Сховище, з’єднання, блокування, реплікація')
pg.add(bargauge('Розмір кожної БД', [(f'sort_by_label(max by (datname, server) (pg_database_size_bytes{{{SHARD_DB}}}), "datname")', '{{datname}} @ {{server}}', 'A', True)],
                'bytes', 'Після перенесення без --drop-source стара копія залишається на джерелі з відкликаними правами.',
                orientation='horizontal', decimals=1), 12, 15)
pg.add(timeseries('З’єднання до БД шардів за сервісами', [
    (f'sum by (server) (pg_stat_activity_count{{{SHARD_DB}}})', 'усього: {{server}}'),
    (f'sum by (server) (pg_stat_activity_count{{{SHARD_DB}, state="active"}})', 'активні: {{server}}')], 'short',
                  'pg_stat_activity: 2 API × 4 БД × пул до 5 з’єднань на кожному сервісі.', overrides=server_overrides('.*: ')), 12, 15)
pg.add(timeseries('Блокування за сервісами (pg_locks)', [(f'sum by (server) (pg_locks_count{{{SHARD_DB}}})', '{{server}}')],
                  'short', 'Кількість блокувань у БД шардів: рядкові блокування UPDATE і FOR UPDATE під навантаженням.',
                  overrides=server_overrides()), 12, 8)
pg.add(timeseries('Реплікація реєстру shard_registry: відставання слотів', [
    ('max by (slot_name) (pg_replication_slot_slot_current_wal_lsn - pg_replication_slot_slot_confirmed_flush_lsn)', '{{slot_name}}')],
    'bytes', 'postgres_00 публікує реєстр сховищ для postgres_01..03 (логічна реплікація).'), 12, 8)


for board in (api, pg):
    path = OUT / f'{board.uid}.json'
    path.write_text(json.dumps(board.json(), indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print('dashboard', path.relative_to(ROOT), len(board.panels), 'panels')
