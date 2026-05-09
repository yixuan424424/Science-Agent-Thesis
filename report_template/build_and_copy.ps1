# 编译 zjuthesis 并将 PDF 复制到 report_template 目录
# 使用前请确保已安装 TeXLive（包含 XeLaTeX 和 latexmk）

$ZjuThesisDir = "C:\Users\EDY\Desktop\zjuthesis"
$OutputDir    = "C:\Users\EDY\Desktop\Final_Project\report_template"
$OutPdf       = "$ZjuThesisDir\out\zjuthesis.pdf"

Write-Host ">>> 开始编译 zjuthesis ..." -ForegroundColor Cyan
Push-Location $ZjuThesisDir

# 使用 latexmk 编译（自动处理多次编译、参考文献等）
latexmk -xelatex -outdir=out zjuthesis.tex

if ($LASTEXITCODE -ne 0) {
    Write-Host "!!! 编译失败，请检查 LaTeX 错误信息。" -ForegroundColor Red
    Pop-Location
    exit 1
}

Pop-Location

Write-Host ">>> 编译成功，复制 PDF 到 report_template ..." -ForegroundColor Green
Copy-Item -Path $OutPdf -Destination "$OutputDir\zjuthesis.pdf" -Force

Write-Host ">>> 完成！PDF 已保存到：$OutputDir\zjuthesis.pdf" -ForegroundColor Green
