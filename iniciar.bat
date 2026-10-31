@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 servidor.py --abrir
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Se necesita Python 3 instalado en este equipo.
    ) else (
        python servidor.py --abrir
    )
)
pause
