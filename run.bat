@echo off
cd /d "%~dp0"
title 自动剪辑+自动发布智能体

:menu
echo.
echo ============================================
echo   自动剪辑 + 自动发布智能体
echo ============================================
echo   [A] ★四平台风格化剪辑（素材→4条不同风格成片，推荐）
echo   [1] 全自动守护（监听inbox + 每天20:00发队列）
echo   [2] 只监听 inbox（剪刀手，剪好排队等发布）
echo   [3] 处理 inbox 里所有素材（跑一次）
echo   [4] 处理单个视频（冒烟测试 dry-run）
echo   [5] 立即发布待发布队列
echo   [6] 查看待发布队列
echo   [7] 预登录平台（首次扫码）
echo   [8] 校准发布页选择器（平台改版时用）
echo   [9] 退出
echo ============================================
set /p choice=请选择 [1-9/A]:

if /i "%choice%"=="A" goto styles
if "%choice%"=="1" goto daemon
if "%choice%"=="2" goto watch
if "%choice%"=="3" goto process
if "%choice%"=="4" goto once
if "%choice%"=="5" goto pubpending
if "%choice%"=="6" goto queue
if "%choice%"=="7" goto login
if "%choice%"=="8" goto probe
if "%choice%"=="9" goto end
goto menu

:styles
python make_styles.py
echo.
echo   四条风格成片已生成在 outbox\styles\ 目录
pause
goto menu

:daemon
python scheduler.py daemon
pause
goto menu

:watch
python pipeline.py watch
pause
goto menu

:process
python pipeline.py process-inbox
pause
goto menu

:once
set /p videopath=输入视频路径（可拖入）:
python pipeline.py once "%videopath%" --dry-run
pause
goto menu

:pubpending
python pipeline.py publish-pending
pause
goto menu

:queue
python pipeline.py queue
pause
goto menu

:login
echo   [d] 抖音  [x] 小红书  [s] 视频号  [k] 快手
set /p p=选择平台字母:
if /i "%p%"=="d" python pipeline.py login douyin
if /i "%p%"=="x" python pipeline.py login xiaohongshu
if /i "%p%"=="s" python pipeline.py login shipinhao
if /i "%p%"=="k" python pipeline.py login kuaishou
pause
goto menu

:probe
echo   [d] 抖音  [x] 小红书  [s] 视频号  [k] 快手  [a] 全部
set /p p=选择平台字母:
if /i "%p%"=="d" python probe_selectors.py douyin
if /i "%p%"=="x" python probe_selectors.py xiaohongshu
if /i "%p%"=="s" python probe_selectors.py shipinhao
if /i "%p%"=="k" python probe_selectors.py kuaishou
if /i "%p%"=="a" python probe_selectors.py all
pause
goto menu

:end
