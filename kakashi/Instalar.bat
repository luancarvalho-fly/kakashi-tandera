@echo off
REM KAKASHI da Fly - instalar na mao (duplo clique). O jeito facil e soltar o zip no Claude Code e pedir "instala o Kakashi".
cd /d "%~dp0"
where py >nul 2>nul && (py -3 instalar.py %*) || (python instalar.py %*)
echo.
pause
