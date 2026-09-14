@echo off
chcp 65001 >nul

echo 检查 Chrome 是否已在运行...
tasklist /fi "IMAGENAME eq chrome.exe" /nh 2>nul | find /i "chrome.exe" >nul
if %errorlevel%==0 (
    echo [WARNING] Chrome 正在运行中，无法启动第二个调试实例。
    echo.
    echo 请先关闭所有 Chrome 窗口，再运行本脚本。
    echo 或直接使用桌面/任务栏的 Chrome 快捷方式打开（需自带调试端口参数）。
    pause
    exit /b 1
)

set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" set "CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" (
    echo [ERROR] 未找到 Chrome，请手动修改本脚本中的 CHROME_PATH
    pause
    exit /b 1
)

echo 正在启动 Chrome（调试端口 9223）...
start "" "%CHROME_PATH%" --remote-debugging-port=9223

echo.
echo Chrome 已启动，调试端口 9223
echo.
echo 请在 Chrome 中打开五个平台的管理后台并保持登录。
echo 平台列表: 公众号 / 头条号 / 百家号 / 知乎 / CSDN
echo.
pause
