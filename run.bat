@echo off
chcp 65001 >nul
echo ============================================
echo  DBManager - Self-use Database Manager
echo ============================================
echo.

REM 第一次运行会自动安装依赖
pip install --quiet -r requirements.txt 2>nul

REM 启动
python main.py

if errorlevel 1 (
    echo.
    echo 程序异常退出,查看日志:
    type "%APPDATA%\DBManager\dbmanager.log" 2>nul | more
    pause
)
