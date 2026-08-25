@echo off
chcp 65001 >nul
echo Building DBManager.exe with PyInstaller...
echo.

pip install --quiet pyinstaller
pyinstaller --clean build.spec

if exist "dist\DBManager\DBManager.exe" (
    echo.
    echo ============================================
    echo  构建成功!
    echo  产物: dist\DBManager\DBManager.exe
    echo ============================================
) else (
    echo.
    echo 构建失败,查看上面的错误
)
pause
