@echo off
chcp 65001 >nul
title 安装依赖

echo ============================================
echo        正在安装项目依赖
echo ============================================
echo.
echo  使用国内镜像源加速下载 ...
echo.

pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo  安装失败，尝试备用镜像源 ...
    echo.
    pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple
)
if errorlevel 1 (
    echo.
    echo ============================================
    echo  安装失败，请检查网络连接。
    echo ============================================
    goto end
)

echo.
echo ============================================
echo  依赖安装完成！
echo ============================================

echo.
echo 正在安装 Chromium 浏览器（Playwright）...
echo 使用国内镜像源 ...
echo.

set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
python -m playwright install chromium
if errorlevel 1 (
    echo.
    echo  镜像源下载失败，尝试官方源 ...
    echo.
    set PLAYWRIGHT_DOWNLOAD_HOST=
    python -m playwright install chromium
)
if errorlevel 1 (
    echo.
    echo ============================================
    echo  浏览器下载失败，可以手动运行:
    echo   python -m playwright install chromium
    echo ============================================
    goto end
)

echo.
echo ============================================
echo  全部安装完成！
echo ============================================

:end
echo.
pause
