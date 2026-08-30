@echo off
rem 汇诊 MedConsult 一键启动：后台起服务并打开浏览器
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [!] 未找到虚拟环境，正在初始化（仅需一次）...
  python -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)
start "MedConsult Server" /min cmd /k ".venv\Scripts\python.exe server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8765"
echo 平台已启动：http://127.0.0.1:8765 （关闭弹出的最小化窗口即可停止服务）
goto :eof
:fail
echo [!] 初始化失败，请检查 Python 是否已安装并在 PATH 中。
pause
