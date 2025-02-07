@echo off
title Iniciando Gestor de URLs

REM Navegar al directorio del script
cd /d "%~dp0"

REM Activar entorno virtual
call env\Scripts\activate || (echo Error al activar el entorno virtual & exit /b)

REM Iniciar el servidor Hypercorn
start cmd /k hypercorn -b 0.0.0.0:5000 App:app || (echo Error al iniciar el servidor & exit /b)

REM Esperar 2 segundos para que el servidor arranque
timeout /t 2 /nobreak >nul

REM Abrir la aplicación en el navegador predeterminado
start http://127.0.0.1:5000/

exit