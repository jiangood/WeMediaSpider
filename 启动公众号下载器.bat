@echo off
chcp 65001 >nul
title 微信公众号文章下载器

:LOOP
cls
echo ============================================
echo       微信公众号文章下载器
echo ============================================
echo.

set /p name=请输入公众号名称（直接回车退出）: 
if "%name%"=="" exit /b

set /p days=请输入要爬取的天数（直接回车默认30天）: 
if "%days%"=="" set days=30

echo.
echo  公众号: %name%
echo  天数:   %days% 天
echo.
echo  正在启动爬虫，请稍候 ...
echo.

python wx_cli.py "%name%" %days%

echo.
echo ============================================
echo  任务执行完毕！
echo ============================================
echo.
echo  按任意键继续（继续下载），或关闭窗口退出 ...
echo.
pause >nul
goto LOOP
