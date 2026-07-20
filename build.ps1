param(
    [switch]$Clean
)

Write-Host "🚀 Building Aegis Executable..." -ForegroundColor Cyan

if ($Clean) {
    Write-Host "🧹 Cleaning old builds..." -ForegroundColor Yellow
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    if (Test-Path "aegis.spec") { Remove-Item -Force "aegis.spec" }
}

Write-Host "📦 Running PyInstaller..." -ForegroundColor Yellow
pyinstaller --onefile --name aegis src/main.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Build Complete! Executable is ready at: dist\aegis.exe" -ForegroundColor Green
} else {
    Write-Host "❌ Build Failed!" -ForegroundColor Red
}
