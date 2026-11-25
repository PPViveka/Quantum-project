# Opens the generated report in Microsoft Word, builds the table of contents,
# saves the .docx and exports a PDF next to it. Windows + Word required.
#   powershell -ExecutionPolicy Bypass -File tools\finalize_report.ps1
param([string]$Docx = "$PSScriptRoot\..\report\Group12_Quantum_Report.docx")

$Docx = (Resolve-Path $Docx).Path
$Pdf = [IO.Path]::ChangeExtension($Docx, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($Docx)
    foreach ($toc in $doc.TablesOfContents) {
        $toc.Update()
        $toc.Range.Font.Name = "Times New Roman"
        $toc.Range.Font.Size = 12
        $toc.Range.Font.Bold = 1
    }
    $doc.Save()
    $doc.ExportAsFixedFormat($Pdf, 17)   # 17 = wdExportFormatPDF
    "Pages: " + $doc.ComputeStatistics(2)
    $doc.Close()
    "Saved $Docx"
    "Saved $Pdf"
} finally {
    $word.Quit()
}
