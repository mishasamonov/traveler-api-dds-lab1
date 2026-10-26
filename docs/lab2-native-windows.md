# Нативний запуск лабораторної 2 у Windows

Baseline вимірюється без Docker і віртуальних машин. База та API працюють
на одному комп’ютері. Перша лабораторна в main не змінена; друга розміщена
в гілці `lab2-performance`.

## Робоче середовище цього запуску

- API: `http://127.0.0.1:4567`, Node.js 22.18.0, пул 20.
- PostgreSQL 16.15: `127.0.0.1:55432`, база `traveler_lab2`.
- Дані й бінарні файли PostgreSQL: `$env:TEMP\dds-lab2-native`.
- k6 2.3.0: `.tools\k6\k6-v2.3.0-windows-amd64\k6.exe` у батьківській
  робочій папці. Бінарні файли не включені до Git або архіву вихідного коду.

У цьому оточенні initdb з кириличного шляху не завершився успішно. Робочий
каталог PostgreSQL перенесено до тимчасового каталогу з латинським шляхом.
Це окремий кластер для лабораторної, а не системна служба чи наявна база.

## Повторний запуск після зупинки

У PowerShell із каталогу проєкту:

```powershell
$pgRoot = Join-Path $env:TEMP 'dds-lab2-native'
& (Join-Path $pgRoot 'pgsql\bin\pg_ctl.exe') -D (Join-Path $pgRoot 'pgdata') -l (Join-Path $pgRoot 'postgres.log') -o '-p 55432 -h 127.0.0.1 -c max_connections=100 -c shared_buffers=128MB' start
$env:DATABASE_URL = 'postgres://traveler@127.0.0.1:55432/traveler_lab2'
node scripts/init-db.js
node src/server.js
```

У другому PowerShell:

```powershell
$env:DATABASE_URL = 'postgres://traveler@127.0.0.1:55432/traveler_lab2'
$k6Path = Join-Path (Split-Path (Get-Location) -Parent) '.tools\k6\k6-v2.3.0-windows-amd64\k6.exe'
./scripts/run-performance.ps1 -Test smoke -K6 $k6Path
./scripts/run-performance.ps1 -Test load -K6 $k6Path
./scripts/run-performance.ps1 -Test stress -K6 $k6Path
./scripts/run-performance.ps1 -Test spike -K6 $k6Path
./scripts/run-performance.ps1 -Test endurance -K6 $k6Path
```

Параметр `-ApiPid` дозволяє зібрати пам’ять саме процесу API. Його PID потрібно
взяти зі свого запущеного процесу Node.js. Без цього параметра HTTP вимірювання
залишаються доступними, але пам’ять API не збирається.

Кожний тест заново готує 2000 планів і 6000 локацій. Скрипт підготовки відмовляє
для будь-якої назви БД, крім `traveler_lab2`. Не запускати тести паралельно.
Після stress і spike код 99 очікуваний, якщо система порушила заданий поріг
затримки. Це результат вимірювання; дивитися також помилки HTTP та відновлення.

## Аналіз і звіт

Python залежності для графіків і документа перелічені в `requirements-report.txt`.
Після всіх запусків:

```powershell
python scripts/analyze-performance.py load stress spike endurance --plot
python scripts/build-lab2-report.py --output ./output/TravelerAPI_Lab2_Samonov.docx
```

Побудова документа потребує `results/commits.json` з посиланням на коміт
endurance. Оригінальні `*-dashboard.html` можна відкрити подвійним клацанням
без запущеного сервера. `*-raw.json.gz` містять всі часові samples і через розмір
зберігаються в локальному архіві результатів, а не в Git.

## Зупинка окремого кластера

Після завершення API через Ctrl+C:

```powershell
$pgRoot = Join-Path $env:TEMP 'dds-lab2-native'
& (Join-Path $pgRoot 'pgsql\bin\pg_ctl.exe') -D (Join-Path $pgRoot 'pgdata') stop -m fast
```

Ця команда зупиняє тільки кластер, чий data directory явно передано в `-D`.
