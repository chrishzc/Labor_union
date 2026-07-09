@echo off
chcp 65001 >nul
title 月子工會系統 - 啟動器
echo ========================================================
echo         啟動 新竹市月子工會自動化管理系統
echo ========================================================
echo.

:: 檢查是否安裝了 uv
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [錯誤] 找不到 uv 套件管理器，請確認是否已安裝並加入環境變數。
    pause
    exit /b 1
)

echo [1/2] 正在背景啟動 API 伺服器 (FastAPI)...
:: 使用 start 開啟新視窗執行，讓 Streamlit 可以在主視窗跑，方便查看個別 log
start "Labor Union API Server" cmd /c "uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --env-file .env"

echo [2/2] 正在啟動管理介面 (Streamlit)...
echo.
echo 提示：啟動成功後將會自動開啟瀏覽器。如需關閉系統，請關閉這兩個黑色命令列視窗即可。
echo.

uv run streamlit run admin/app.py

pause
