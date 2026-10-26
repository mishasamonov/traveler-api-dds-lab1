param(
  [ValidateSet('smoke','load','stress','spike','endurance')][string]$Test = 'smoke',
  [string]$K6 = 'k6',
  [int]$ApiPid = 0
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
if (!$env:DATABASE_URL) { throw 'Set DATABASE_URL to the disposable traveler_lab2 database first' }
node scripts/seed-performance.cjs
if ($LASTEXITCODE -ne 0) { throw 'Database seed failed' }
$dir = 'tests/performance-tests/results'
New-Item -ItemType Directory -Force $dir | Out-Null
$env:K6_WEB_DASHBOARD = 'true'
$env:K6_WEB_DASHBOARD_PORT = '-1'
$env:K6_WEB_DASHBOARD_PERIOD = '5s'
$env:K6_WEB_DASHBOARD_EXPORT = "$dir/$Test-dashboard.html"
$env:RESULT_DIR = $dir
$start = [DateTimeOffset]::UtcNow
$metadata = [ordered]@{
  test = $Test; startedUtc = $start.ToString('o'); apiUrl = 'http://127.0.0.1:4567';
  database = 'traveler_lab2'; seedPlans = 2000; seedLocations = 6000;
  node = (node --version); k6 = (& $K6 version); pgPoolMax = 20;
  databaseMode = 'native Windows PostgreSQL, no virtualization';
  command = "k6 run --out json=$dir/$Test-raw.json.gz tests/performance-tests/$Test-test.js"
}
$metadata.apiPid = $ApiPid
$process = Start-Process -FilePath $K6 -ArgumentList @('run','--out',"json=$dir/$Test-raw.json.gz","tests/performance-tests/$Test-test.js") -WorkingDirectory $repo -RedirectStandardOutput "$dir/$Test-console.txt" -RedirectStandardError "$dir/$Test-stderr.txt" -WindowStyle Hidden -PassThru
$csv = Join-Path $repo "$dir/$Test-resources.csv"
do {
  $time = [DateTimeOffset]::UtcNow.ToString('o')
  $apiSample = if ($ApiPid) { @(Get-Process -Id $ApiPid -ErrorAction SilentlyContinue) } else { @() }
  $sample = @(Get-Process -Id $process.Id -ErrorAction SilentlyContinue) + $apiSample + @(Get-Process postgres -ErrorAction SilentlyContinue)
  $sample | Select-Object @{n='timestamp';e={$time}},Id,ProcessName,CPU,WorkingSet64,PrivateMemorySize64,Threads | ForEach-Object {
    $_.Threads = $_.Threads.Count
    $_
  } | Export-Csv -LiteralPath $csv -NoTypeInformation -Append -Encoding utf8
  Start-Sleep -Seconds 5
  $process.Refresh()
} while (!$process.HasExited)
$process.WaitForExit()
$metadata.finishedUtc = [DateTimeOffset]::UtcNow.ToString('o')
$metadata.exitCode = $process.ExitCode
$metadata.elapsedSeconds = ([DateTimeOffset]::UtcNow - $start).TotalSeconds
$metadata | ConvertTo-Json | Set-Content "$dir/$Test-run.json" -Encoding utf8
node scripts/check-performance-data.cjs $Test
Get-Content "$dir/$Test-summary.txt"
Write-Output "k6 exit code: $($process.ExitCode)"
exit $process.ExitCode
