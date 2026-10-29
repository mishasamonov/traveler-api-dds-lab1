param([Parameter(Mandatory=$true)][string]$DocxPath,[Parameter(Mandatory=$true)][string]$PdfPath)
$ErrorActionPreference='Stop'
$source=(Resolve-Path -LiteralPath $DocxPath).Path
$destination=[System.IO.Path]::GetFullPath($PdfPath)
New-Item -ItemType Directory -Force ([System.IO.Path]::GetDirectoryName($destination)) | Out-Null
$word=$null;$document=$null
try {
 $word=New-Object -ComObject Word.Application
 $word.Visible=$false;$word.DisplayAlerts=0
 $document=$word.Documents.Open($source,$false,$true,$false)
 $document.Fields.Update() | Out-Null
 $document.Repaginate()
 $pages=$document.ComputeStatistics(2)
 $document.ExportAsFixedFormat($destination,17)
 [pscustomobject]@{pdf=$destination;pages=$pages} | ConvertTo-Json
} finally {
 if($document){$document.Close($false);[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)}
 if($word){$word.Quit();[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)}
}
