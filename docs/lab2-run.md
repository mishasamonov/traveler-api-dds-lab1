# Лабораторна робота 2

Гілка `lab2-k6` продовжує TravelerAPI з ЛР1. Стан зданої ЛР1 у `main` збережено.

## Що додано

- `tests/performance-tests/smoke-test.js`: адаптований приклад викладача, перевірка health та `version` локацій.
- `load-test.js`: сходинки 25, 50, 100, 200 VU; 3 хв 30 с.
- `stress-test.js`: сходинки 25, 100, 250, 500, 1000, 2000 VU та повернення до 25; 3 хв 50 с.
- `spike-test.js`: 25 → 1000 за 1 с, 20 с піку, повернення до 25 та 60 с спостереження; 2 хв 2 с.
- `endurance-test.js`: 30 с наростання, 29 хв сталого рівня 25 VU, 30 с зниження; разом 30 хв.
- `provided/`: приклади з репозиторію викладача. Для звіту запускаються п’ять файлів у корені performance-tests.
- `utils/workload.js`: спільний сценарій та фіксований набір зі 100 планів із 3 локаціями.
- `.github/workflows/performance.yml`: GitHub Actions без Docker services, PostgreSQL 16 як звичайний процес.
- `scripts/run-performance.sh`: лог, JSON та самодостатній HTML dashboard k6.

Кожні п’ять ітерацій користувача містять 3 читання плану, 1 читання списку та 1 приватний CRUD маршрут із 6 запитами. Між ітераціями є пауза 1 с. Загалом 5 із 10 запитів читають, 5 змінюють дані. Записи виконуються у власний тимчасовий план, тому випадкові конфлікти спільних даних не спотворюють вимірювання. Smoke окремо перевіряє навмисний 409 для застарілої версії локації. Очікувані 404/409 не рахуються як помилки HTTP.

## Запуск на звичайному комп’ютері

Для Windows підготовлено [простий автоматизований запуск](lab2-windows.md): після встановлення Node.js, PostgreSQL та k6 виконайте `npm.cmd ci`, далі `npm.cmd run lab2:local`. Він використовує окрему нову БД ЛР2, сам запускає API й усі п’ять тестів, зберігає кожен запуск у новий каталог `reports/local-…`. Нижче залишено ручний спосіб для перевірки й інших середовищ.

Для baseline за методичкою API, k6 та PostgreSQL потрібно запускати на одному фізичному комп’ютері без Docker і віртуальної машини. Результати GitHub Actions є перевіркою CI; runner є віртуальною машиною, тому його числа не можна видавати за вимірювання фізичного ПК.

1. Встановити Node.js 24, PostgreSQL 16 і k6 1.3.0.
2. Скопіювати репозиторій і перейти в потрібну гілку:

```bash
git clone https://github.com/mishasamonov/traveler-api-dds-lab1.git
cd traveler-api-dds-lab1
git switch lab2-k6
npm ci
```

3. У PostgreSQL створити окрему тестову БД. Приклад SQL:

```sql
CREATE ROLE traveler LOGIN PASSWORD 'traveler';
CREATE DATABASE traveler OWNER traveler;
```

4. У першому терміналі запустити API. За замовчуванням він використовує `postgres://traveler:traveler@localhost:5432/traveler`, порт API `4567`, пул `20` з’єднань:

```bash
npm run db:init
npm start
```

5. В іншому терміналі з кореня репозиторію запустити сценарій. Нижче команди працюють у Linux/macOS/Git Bash:

```bash
bash scripts/run-performance.sh smoke
bash scripts/run-performance.sh load
bash scripts/run-performance.sh stress
bash scripts/run-performance.sh spike
bash scripts/run-performance.sh endurance
```

Або всі по черзі:

```bash
bash scripts/run-performance-suite.sh
```

Запуск без Bash, зокрема у Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force tests/performance-tests/reports | Out-Null
$env:API_URL = 'http://127.0.0.1:4567'
$env:REPORT_DIR = 'tests/performance-tests/reports'
$env:TEST_NAME = 'smoke'
$env:K6_WEB_DASHBOARD = 'true'
$env:K6_WEB_DASHBOARD_PORT = '-1'
$env:K6_WEB_DASHBOARD_PERIOD = '2s'
$env:K6_WEB_DASHBOARD_EXPORT = 'tests/performance-tests/reports/smoke-dashboard.html'
k6 run tests/performance-tests/smoke-test.js 2>&1 | Tee-Object tests/performance-tests/reports/smoke.log
```

Для іншого сценарію замінити `smoke` на `load`, `stress`, `spike` або `endurance` у трьох відповідних місцях. Endurance справді займає 30 хвилин, завершення поточних ітерацій та setup/teardown додають кілька секунд.

## Як читати результати

Файли зберігаються в `tests/performance-tests/reports/`:

- `*-summary.json`: агреговані метрики та значення по фазах.
- `*.log`: точний вивід k6.
- `*-dashboard.html`: відкрити звичайним браузером; графіки часу відповіді, помилок, запитів і VU.
- `exit-codes.txt`: коди завершення повного циклу.

У CI цей каталог прикріплюється до запуску як artifact `lab2-k6-results`. Код `99` у Stress/Spike означає перевищення порогу продуктивності; сам тест завершився й зберіг результати. Smoke/Load/Endurance мають відповідати порогам, інакше перевірка CI позначається невдалою.

Критерії: p95 читань < 500 мс, p95 записів < 1000 мс, частка неочікуваних HTTP помилок < 1%, успішність checks > 99%. Для окремих фаз додатково перевіряється загальний p95 < 1000 мс. Найбільша протестована кількість VU є межею перевіреного діапазону; абсолютну межу API можна назвати лише якщо відповідне порушення фактично зафіксоване.

Додатково виконано GitHub Actions (+1) та експорт у dashboard k6 як аналогічний інструмент графіків (+1). Експерименти з рівнями ізоляції та кешем до цієї роботи не входять.


## Розширений Stress

Для пошуку межі після основного циклу додано `tests/stress-probe/stress-limit-test.js` зі стадіями 25, 1000, 2000, 4000, 8000 VU та відновленням до 25. Тривалість стадій — 3 хв 20 с. Автоматичний запуск — `.github/workflows/stress-probe.yml`. Він запускається окремо і не повторює Endurance.

```bash
mkdir -p tests/performance-tests/reports
TEST_NAME=stress-probe K6_WEB_DASHBOARD=true K6_WEB_DASHBOARD_PORT=-1 K6_WEB_DASHBOARD_PERIOD=2s K6_WEB_DASHBOARD_EXPORT=tests/performance-tests/reports/stress-probe-dashboard.html k6 run tests/stress-probe/stress-limit-test.js
```

У Windows PowerShell задайте `$env:TEST_NAME = "stress-probe"` та відповідний шлях `$env:K6_WEB_DASHBOARD_EXPORT`, після чого виконайте `k6 run tests/stress-probe/stress-limit-test.js`.

Зведення фактичних результатів: [lab2-results/README.md](lab2-results/README.md).
