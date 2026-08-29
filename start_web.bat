@echo off
rem 汇诊 MedConsult 一键启动：后台起服务并打开浏览器
cd /d "%~dp0"
start "MedConsult Server" /min cmd /k ".venv\Scripts\python.exe server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8765"
echo 平台已启动：http://127.0.0.1:8765 （关闭弹出的最小化窗口即可停止服务）
