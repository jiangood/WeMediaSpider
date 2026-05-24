@echo off
chcp 65001 >nul
title 微信公众号文章下载器

if exist .last_name (
    set /p name=<.last_name
) else (
    set name=中铁文旅
)
set days=7

:LOOP
cls
echo ============================================
echo       微信公众号文章下载器
echo ============================================
echo.
echo  上次配置: %name%
echo.

set /p name=请输入公众号名称（回车保持上次）: 
set /p days=请输入要爬取的天数（回车默认 7 天）: 

if "%name%"=="" set name=中铁文旅
if "%days%"=="" set days=7

echo %name% >.last_name

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
