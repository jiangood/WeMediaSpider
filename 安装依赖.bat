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

if %errorlevel% neq 0 (
    echo.
    echo  安装失败，尝试备用镜像源 ...
    echo.
    pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple
)

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo  依赖安装完成！
    echo ============================================
) else (
    echo.
    echo ============================================
    echo  安装失败，请检查网络连接。
    echo ============================================
)

echo.
pause
