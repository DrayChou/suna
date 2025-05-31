@echo off
chcp 65001 >nul
echo ========================================
echo    Suna 开源版本 - 快速启动脚本
echo ========================================
echo.

echo 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.9+
    pause
    exit /b 1
)

echo 检查Docker环境...
docker --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Docker，请先安装Docker Desktop
    pause
    exit /b 1
)

echo 检查Docker Compose...
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Docker Compose，请确保Docker Desktop已正确安装
    pause
    exit /b 1
)

echo.
echo 环境检查通过！
echo.

echo 安装Python依赖...
if not exist "scripts\requirements.txt" (
    echo [错误] 找不到scripts\requirements.txt文件
    pause
    exit /b 1
)

pip install -r scripts\requirements.txt
if errorlevel 1 (
    echo [错误] 安装启动脚本依赖失败
    pause
    exit /b 1
)

echo.
echo 启动Suna开源版本...
echo.

python scripts\start-opensource.py start

echo.
echo 按任意键退出...
pause >nul