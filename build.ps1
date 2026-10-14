# Builds dist\RO Loot Filter.exe (single-file, windowed). Needs: pip install pyinstaller customtkinter pillow lupa
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name "RO Loot Filter" `
  --icon assets\rolf.ico `
  --add-data "filter.toml;." `
  --add-data "assets\rolf.ico;assets" `
  --collect-all customtkinter `
  --hidden-import lupa.lua51 --collect-binaries lupa `
  rolfgui.py
Get-Item "dist\RO Loot Filter.exe" | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
