# Run only after selecting and inspecting the intended Notepad window with Computer Use.
param([Parameter(Mandatory=$true)][string]$Name,[Parameter(Mandatory=$true)][string]$SourceFile,[int]$LogicalWidth=1141)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$workspace=Split-Path $repo -Parent
$captureFolder='D:\Documents\ShareX\Screenshots\'+(Get-Date -Format 'yyyy-MM')
$oldFiles=@(Get-ChildItem -LiteralPath $captureFolder -File | ForEach-Object FullName)
Start-Sleep -Seconds 4 # Let the previous local ShareX preview disappear.
Start-Process -FilePath 'C:\Program Files\ShareX\ShareX.exe' -ArgumentList '-ActiveWindow' -WindowStyle Hidden
$newCapture=$null
for($attempt=0;$attempt -lt 20;$attempt++) {
  Start-Sleep -Milliseconds 250
  $newCapture=Get-ChildItem -LiteralPath $captureFolder -File | Where-Object {$_.FullName -notin $oldFiles} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if($newCapture){break}
}
if(!$newCapture){throw 'No new ShareX capture'}
$rawDir=Join-Path $workspace '.tools\captures'
$outDir=Join-Path $repo 'tests\performance-tests\screenshots'
New-Item -ItemType Directory -Force $rawDir,$outDir | Out-Null
$rawPath=Join-Path $rawDir ($Name+'-full.png')
$outPath=Join-Path $outDir ($Name+'.png')
Copy-Item -LiteralPath $newCapture.FullName -Destination $rawPath -Force
$python='C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -c 'from PIL import Image; import sys; p=Image.open(sys.argv[1]); assert p.format=="PNG",p.format; scale=p.width/int(sys.argv[3]); box=(round(8*scale),round(76*scale),p.width-round(8*scale),p.height-round(32*scale)); p.crop(box).save(sys.argv[2]); print("PNG",p.size,"crop",box)' $rawPath $outPath $LogicalWidth
if($LASTEXITCODE -ne 0){throw 'Screenshot format verification failed'}
$entry=[ordered]@{name=$Name;sourceFile=$SourceFile;capturedUtc=[DateTimeOffset]::UtcNow.ToString('o');sharexFile=$newCapture.Name;rawSha256=(Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash;sourceSha256=(Get-FileHash -LiteralPath (Join-Path $repo $SourceFile) -Algorithm SHA256).Hash;pngSha256=(Get-FileHash -LiteralPath $outPath -Algorithm SHA256).Hash;method='ShareX ActiveWindow; lossless body crop; no resampling or content editing'}
$entry | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outDir ($Name+'-capture.json')) -Encoding utf8
$outPath
