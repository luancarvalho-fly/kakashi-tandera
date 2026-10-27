@echo off
REM KAKASHI + TANDERA da Fly - instala tudo com dois cliques (Windows 10/11). Sem administrador.
REM Se faltar o Python, instala o Python 3.12 so pra este usuario (winget) e segue.
chcp 65001 >nul
cd /d "%~dp0"
title KAKASHI + TANDERA - instalar
echo.
echo   =============================================
echo     KAKASHI + TANDERA (Fly) - instalacao
echo   =============================================
echo.
call :achar_python
if not defined PY (
    where winget >nul 2>nul || goto :sem_winget
    echo   Falta o Python. Instalando o Python 3.12 so pra voce ^(sem administrador^)...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    call :achar_python
)
if not defined PY goto :sem_python
"%PY%" instalar_tudo.py %*
echo.
pause
exit /b

:achar_python
set "PY="
for %%v in (313 312 311 310) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
)
if defined PY exit /b
for /f "delims=" %%p in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%p"
exit /b

:sem_winget
echo   [X] Falta o Python e este Windows nao tem o winget pra instalar sozinho.
echo       Instale o Python 3.12 em python.org (marque "Add python.exe to PATH") e de dois cliques aqui de novo.
pause
exit /b 1

:sem_python
echo   [X] Nao consegui instalar o Python. Instale o Python 3.12 em python.org e de dois cliques aqui de novo.
pause
exit /b 1
