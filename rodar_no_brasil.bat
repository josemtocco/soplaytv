@echo off
REM ============================================================
REM  Gera a lista M3U do SO Play a partir do SEU PC no Brasil.
REM  Use este script para a PRIMEIRA geracao (catalogo completo),
REM  pois o GitHub Actions roda em IP fora do Brasil.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

REM --- Opcional: cole aqui o endpoint/token capturados no F12 > Network ---
REM set SOPLAY_API=https://.../api/...
REM set SOPLAY_TOKEN=Bearer eyJ...

REM Testar se cada stream responde (recomendado no Brasil):
set SOPLAY_CHECK=1

REM Debug (salva respostas cruas em debug_soplay\):
REM set SOPLAY_DEBUG=1

python gerar_soplay.py
if errorlevel 1 (
  echo.
  echo [ERRO] Falha ao gerar. Se aparecer erro de fonte, capture o endpoint
  echo        real no navegador (F12 ^> Network) e defina SOPLAY_API acima.
)

echo.
echo Arquivo gerado em playlists\soplay.m3u
pause
