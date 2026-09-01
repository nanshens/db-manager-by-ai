@echo off
chcp 65001 >nul
echo Building DBManager.exe with PyInstaller...
echo.

REM 确认 PyInstaller 已装
.venv\Scripts\python.exe -m pip install --quiet --upgrade pyinstaller

REM 清旧的 build / dist(确保全新构建)
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm build.spec

if exist "dist\DBManager.exe" (
    echo.
    echo ============================================
    echo  构建成功!
    echo  产物: dist\DBManager.exe
    for %%I in ("dist\DBManager.exe") do echo  大小: %%~zI bytes (约 %%~zI / 1048576 MB)
    echo ============================================
) else (
    echo.
    echo 构建失败,查看上面的错误
)
pause
