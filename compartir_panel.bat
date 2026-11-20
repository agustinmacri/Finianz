@echo off
rem Comparte el panel web por internet con un tunel de Cloudflare (link https://....trycloudflare.com).
rem Requisitos: cloudflared instalado (winget install --id Cloudflare.cloudflared) y PANEL_CLAVE en el .env.
rem El link sirve mientras esta ventana y la del panel esten abiertas; cambia cada vez.
cd /d "%~dp0"
findstr /b /c:"PANEL_CLAVE=" .env >nul
if errorlevel 1 (
  echo Falta PANEL_CLAVE en el .env: el panel quedaria abierto a cualquiera con el link. No se comparte.
  pause
  exit /b 1
)
start "Panel de renta fija" ".venv\Scripts\python.exe" -m streamlit run web\app.py --server.headless true
timeout /t 6 >nul
echo.
echo Busca abajo la linea con https://....trycloudflare.com : ese es el link para compartir.
echo Para cortar: Ctrl+C aca y cerrar la ventana del panel.
echo.
cloudflared tunnel --url http://localhost:8501
