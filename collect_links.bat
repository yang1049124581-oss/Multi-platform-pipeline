@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ========================================
echo  五平台链接汇总工具 - CDP 版
echo  全自动提取（无需手动操作）
echo  请确保浏览器已启动调试端口（Chrome 9223 / Edge 9222）
echo ========================================
echo.
set /p TITLES="请输入当天文章标题（逗号分隔）: "
python scripts\cdp_collect.py --titles "%TITLES%"
pause
