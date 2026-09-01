@echo off
chcp 65001 >nul
echo Building DBManager.exe with PyInstaller...
echo.

REM 升级 PyInstaller(Python 3.13 + PySide6 6.11 需要最新版 hook 修 DLL 收集问题)
.venv\Scripts\python.exe -m pip install --quiet --upgrade pyinstaller

REM 清旧的 build / dist
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm build.spec

if exist "dist\DBManager.exe" (
    echo.
    echo ============================================
    echo  构建成功!
    echo  产物: dist\DBManager.exe
    echo  数据目录: dist\DBManagerData\  ^(首次启动时自动创建^)
    for %%I in ("dist\DBManager.exe") do echo  大小: %%~zI bytes (~%%~zI / 1048576 MB)
    echo ============================================
) else (
    echo.
    echo 构建失败,查看上面的错误
)
pause
