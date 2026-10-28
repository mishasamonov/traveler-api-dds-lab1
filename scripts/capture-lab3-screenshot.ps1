# Select, inspect and foreground the intended app using Computer Use before calling.
param([Parameter(Mandatory=$true)][string]$Name,[string]$SourceFile='',[int]$Top=110,[int]$Bottom=900)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$workspace=Split-Path $repo -Parent
$captureFolder='D:\Documents\ShareX\Screenshots\'+(Get-Date -Format 'yyyy-MM')
$previous=@(Get-ChildItem -LiteralPath $captureFolder -File | ForEach-Object FullName)
Start-Process -FilePath 'C:\Program Files\ShareX\ShareX.exe' -ArgumentList '-ActiveWindow' -WindowStyle Hidden
$found=$null
for($n=0;$n -lt 20;$n++) {
 Start-Sleep -Milliseconds 250
 $found=Get-ChildItem -LiteralPath $captureFolder -File | Where-Object {$_.FullName -notin $previous} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
 if($found){break}
}
if(!$found){throw 'No new ShareX capture'}
$raw=Join-Path $workspace ('.tools\lab3\captures\'+$Name+'-full.png')
$out=Join-Path $repo ('evidence\screenshots\'+$Name+'.png')
New-Item -ItemType Directory -Force (Split-Path $raw),(Split-Path $out) | Out-Null
Copy-Item -LiteralPath $found.FullName -Destination $raw -Force
& 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 -c 'from PIL import Image;import sys;im=Image.open(sys.argv[1]);assert im.format=="PNG";im.crop((0,int(sys.argv[3]),im.width,min(im.height,int(sys.argv[4])))).save(sys.argv[2]);print(im.format,im.size)' $raw $out $Top $Bottom
if($LASTEXITCODE -ne 0){throw 'PNG verification failed'}
$entry=[ordered]@{name=$Name;capturedUtc=[DateTimeOffset]::UtcNow.ToString('o');sourceFile=$SourceFile;sharexFile=$found.Name;rawSha256=(Get-FileHash -LiteralPath $raw).Hash;pngSha256=(Get-FileHash -LiteralPath $out).Hash;cropTop=$Top;cropBottom=$Bottom;method='ShareX ActiveWindow; lossless crop; no resampling or content editing'}
if($SourceFile){$entry.sourceSha256=(Get-FileHash -LiteralPath (Join-Path $repo $SourceFile)).Hash}
$entry|ConvertTo-Json|Set-Content ($out.Replace('.png','-capture.json')) -Encoding utf8
Write-Output $out
