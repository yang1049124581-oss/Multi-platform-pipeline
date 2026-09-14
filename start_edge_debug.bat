@echo off
chcp 65001 >nul

echo 检查 Edge 是否已在运行...
tasklist /fi "IMAGENAME eq msedge.exe" /nh 2>nul | find /i "msedge.exe" >nul
if %errorlevel%==0 (
    echo [WARNING] Edge 正在运行中，无法启动第二个实例。
    echo.
    echo 请先关闭所有 Edge 窗口，再运行本脚本。
    echo 或直接使用桌面/任务栏的 Edge 快捷方式打开（已自带调试端口）。
    pause
    exit /b 1
)

echo 正在启动 Edge（调试端口 9222）...
python -c "import subprocess,os; paths=[r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',os.path.join(os.environ.get('LOCALAPPDATA',''),r'Microsoft\Edge\Application\msedge.exe')]; exe=next((p for p in paths if os.path.exists(p)),None); subprocess.Popen([exe,'--remote-debugging-port=9222']); print('Edge 已启动，调试端口 9222')"

echo.
echo 请在 Edge 中打开五个平台的管理后台并保持登录。
echo 平台列表: 公众号 / 头条号 / 百家号 / 知乎 / CSDN
echo.
pause
